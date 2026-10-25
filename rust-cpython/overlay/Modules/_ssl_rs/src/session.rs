use rustls::client::{Tls12ClientSessionValue, Tls13ClientSessionValue};
use std::cell::RefCell;
use std::fmt;
use std::marker::PhantomData;
use std::rc::Rc;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

static NEXT_CONTEXT_ID: AtomicU64 = AtomicU64::new(1);

pub(crate) struct SessionStats {
    client_connections: AtomicU64,
    client_successes: AtomicU64,
    server_connections: AtomicU64,
    server_successes: AtomicU64,
    resumption_hits: AtomicU64,
}

impl SessionStats {
    pub(crate) fn new() -> Self {
        Self {
            client_connections: AtomicU64::new(0),
            client_successes: AtomicU64::new(0),
            server_connections: AtomicU64::new(0),
            server_successes: AtomicU64::new(0),
            resumption_hits: AtomicU64::new(0),
        }
    }

    pub(crate) fn client_started(&self) {
        self.client_connections.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn client_completed(&self) {
        self.client_successes.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn server_started(&self) {
        self.server_connections.fetch_add(1, Ordering::Relaxed);
    }

    pub(crate) fn server_completed(&self, reused: bool) {
        self.server_successes.fetch_add(1, Ordering::Relaxed);
        if reused {
            self.resumption_hits.fetch_add(1, Ordering::Relaxed);
        }
    }

    pub(crate) fn snapshot(&self, number: usize) -> std::collections::HashMap<String, u64> {
        std::collections::HashMap::from([
            ("number".to_string(), number as u64),
            ("connect".to_string(), self.client_connections.load(Ordering::Relaxed)),
            ("connect_good".to_string(), self.client_successes.load(Ordering::Relaxed)),
            ("connect_renegotiate".to_string(), 0),
            ("accept".to_string(), self.server_connections.load(Ordering::Relaxed)),
            ("accept_good".to_string(), self.server_successes.load(Ordering::Relaxed)),
            ("accept_renegotiate".to_string(), 0),
            ("hits".to_string(), self.resumption_hits.load(Ordering::Relaxed)),
            ("misses".to_string(), 0),
            ("timeouts".to_string(), 0),
            ("cache_full".to_string(), 0),
        ])
    }
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct ContextIdentity(u64);

impl ContextIdentity {
    pub(crate) fn new() -> Arc<Self> {
        Arc::new(Self(NEXT_CONTEXT_ID.fetch_add(1, Ordering::Relaxed)))
    }
}

pub(crate) enum ClientSessionValue {
    Tls12(Tls12ClientSessionValue),
    Tls13(Tls13ClientSessionValue),
}

enum SessionValue {
    Tls12(Tls12ClientSessionValue),
    Tls13Ticket(Option<Tls13ClientSessionValue>),
    Tls13WithoutTicket,
}

const NONRESUMABLE_SESSION_TIMEOUT: u32 = 7200;

struct SessionMetadata {
    id: Vec<u8>,
    time: u64,
    timeout: u32,
    has_ticket: bool,
    ticket_lifetime_hint: u32,
}

pub(crate) struct SessionData {
    pub(crate) context: Arc<ContextIdentity>,
    pub(crate) server_name: String,
    pub(crate) verified_chain: Option<Vec<Vec<u8>>>,
    metadata: SessionMetadata,
    value: Mutex<SessionValue>,
}

impl SessionData {
    pub(crate) fn same_id(&self, other: &Self) -> bool {
        self.metadata.id == other.metadata.id
    }

    pub(crate) fn binding_metadata(&self) -> (&[u8], u64, u32, bool, u32) {
        (
            &self.metadata.id,
            self.metadata.time,
            self.metadata.timeout,
            self.metadata.has_ticket,
            self.metadata.ticket_lifetime_hint,
        )
    }

    pub(crate) fn new(
        value: ClientSessionValue,
        context: Arc<ContextIdentity>,
        server_name: String,
        verified_chain: Option<Vec<Vec<u8>>>,
    ) -> Self {
        let metadata = match &value {
            ClientSessionValue::Tls12(value) => SessionMetadata {
                id: value.session_id().to_vec(),
                time: value.time(),
                timeout: value.timeout(),
                has_ticket: value.has_ticket(),
                ticket_lifetime_hint: value.ticket_lifetime_hint(),
            },
            ClientSessionValue::Tls13(value) => SessionMetadata {
                id: Vec::new(),
                time: value.time(),
                timeout: value.timeout(),
                has_ticket: value.has_ticket(),
                ticket_lifetime_hint: value.ticket_lifetime_hint(),
            },
        };
        let value = match value {
            ClientSessionValue::Tls12(value) => SessionValue::Tls12(value),
            ClientSessionValue::Tls13(value) => SessionValue::Tls13Ticket(Some(value)),
        };
        Self {
            context,
            server_name,
            verified_chain,
            metadata,
            value: Mutex::new(value),
        }
    }

    pub(crate) fn new_tls13_without_ticket(
        context: Arc<ContextIdentity>,
        server_name: String,
        verified_chain: Option<Vec<Vec<u8>>>,
        time: u64,
    ) -> Self {
        Self {
            context,
            server_name,
            verified_chain,
            metadata: SessionMetadata {
                id: Vec::new(),
                time,
                timeout: NONRESUMABLE_SESSION_TIMEOUT,
                has_ticket: false,
                ticket_lifetime_hint: 0,
            },
            value: Mutex::new(SessionValue::Tls13WithoutTicket),
        }
    }

    pub(crate) fn reserve_explicit(
        self: &Arc<Self>,
    ) -> Result<Arc<ExplicitSession>, SessionUseError> {
        let value = match &mut *self.value.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) {
            SessionValue::Tls12(value) => SessionValue::Tls12(value.clone()),
            SessionValue::Tls13Ticket(ticket) => SessionValue::Tls13Ticket(Some(
                ticket.take().ok_or(SessionUseError::Tls13TicketAlreadyUsed)?,
            )),
            SessionValue::Tls13WithoutTicket => SessionValue::Tls13WithoutTicket,
        };
        Ok(Arc::new(ExplicitSession {
            data: Arc::clone(self),
            value: Mutex::new(value),
        }))
    }
}

#[derive(Debug, Clone, Copy)]
pub(crate) enum SessionUseError {
    Tls13TicketAlreadyUsed,
}

impl fmt::Display for SessionUseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Tls13TicketAlreadyUsed => f.write_str("TLS 1.3 session ticket has already been used"),
        }
    }
}

pub(crate) struct ExplicitSession {
    data: Arc<SessionData>,
    value: Mutex<SessionValue>,
}

impl ExplicitSession {
    pub(crate) fn session_data(&self) -> Arc<SessionData> {
        Arc::clone(&self.data)
    }

    pub(crate) fn tls12_clone(&self, server_name: &str) -> Option<Tls12ClientSessionValue> {
        if self.data.server_name != server_name {
            return None;
        }
        match &*self.value.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) {
            SessionValue::Tls12(value) => Some(value.clone()),
            SessionValue::Tls13Ticket(_) | SessionValue::Tls13WithoutTicket => None,
        }
    }

    pub(crate) fn tls13_take(&self, server_name: &str) -> Option<Tls13ClientSessionValue> {
        if self.data.server_name != server_name {
            return None;
        }
        let mut value = self.value.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        match &mut *value {
            SessionValue::Tls13Ticket(ticket) => ticket.take(),
            SessionValue::Tls13WithoutTicket => None,
            SessionValue::Tls12(_) => None,
        }
    }
}

impl Drop for ExplicitSession {
    fn drop(&mut self) {
        let SessionValue::Tls13Ticket(ticket) = self.value.get_mut().unwrap_or_else(|poisoned| poisoned.into_inner()) else {
            return;
        };
        let Some(ticket) = ticket.take() else {
            return;
        };
        let mut stored = self.data.value.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        if let SessionValue::Tls13Ticket(current) = &mut *stored {
            if current.is_none() {
                *current = Some(ticket);
            }
        }
    }
}

thread_local! {
    static SESSION_CAPTURE: RefCell<Option<Arc<Mutex<Option<Arc<SessionData>>>>>> = const { RefCell::new(None) };
    static SESSION_OVERRIDE: RefCell<Option<Arc<ExplicitSession>>> = const { RefCell::new(None) };
}

pub(crate) struct SessionCapture {
    previous: Option<Arc<Mutex<Option<Arc<SessionData>>>>>,
    _not_send: PhantomData<Rc<()>>,
}

impl SessionCapture {
    pub(crate) fn enter(target: Arc<Mutex<Option<Arc<SessionData>>>>) -> Self {
        let previous = SESSION_CAPTURE.with(|current| current.replace(Some(target)));
        Self {
            previous,
            _not_send: PhantomData,
        }
    }
}

impl Drop for SessionCapture {
    fn drop(&mut self) {
        let previous = self.previous.take();
        SESSION_CAPTURE.with(|current| {
            current.replace(previous);
        });
    }
}

pub(crate) fn capture_current_session(session: Arc<SessionData>) {
    SESSION_CAPTURE.with(|current| {
        if let Some(target) = current.borrow().as_ref() {
            *target.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(session);
        }
    });
}

pub(crate) struct SessionOverride {
    previous: Option<Arc<ExplicitSession>>,
    _not_send: PhantomData<Rc<()>>,
}

impl SessionOverride {
    pub(crate) fn enter(session: Arc<ExplicitSession>) -> Self {
        let previous = SESSION_OVERRIDE.with(|current| current.replace(Some(session)));
        Self {
            previous,
            _not_send: PhantomData,
        }
    }
}

impl Drop for SessionOverride {
    fn drop(&mut self) {
        let previous = self.previous.take();
        SESSION_OVERRIDE.with(|current| {
            current.replace(previous);
        });
    }
}

pub(crate) fn current_session_override() -> Option<Arc<ExplicitSession>> {
    SESSION_OVERRIDE.with(|current| current.borrow().as_ref().map(Arc::clone))
}
