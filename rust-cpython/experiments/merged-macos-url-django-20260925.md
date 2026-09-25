# Merged macOS URL candidate on Django requests

**Keep the optional unquote route as a targeted speed experiment; these Django requests show no established application gain.** The matched quote-only and opt-in unquote CPython 3.16 installations from the [merged macOS comparison](merged-macos-url-comparison-20260925.md) ran the approved Django 6.1.1, asgiref 3.12.1, and sqlparse 0.6.0 inputs. The unquote route improved the URL-heavy search-form task in that comparison, but neither complete Django WSGI task shows a gain beyond local noise here.

| Workload | Quote-only self wall | Unquote versus quote-only wall | Root CPU change | Peak RSS median change |
| --- | ---: | ---: | ---: | ---: |
| Cold first request, fresh process | −0.77% | +2.69% | +1.38% | −262,144 B |
| Warm WSGI request | −2.29% | +2.12% | +0.56% | +81,920 B |

The cold comparison's five paired wall ratios had a median of 1.0269 against an 11.74% timing noise allowance; the warm comparison's median was 1.0212 against a 6.60% allowance. Both tasks produced the same full response digest on every attempt. Both cold runs used an unchanged, byte-hashed 3,919,872-byte SQLite fixture. The three separate memory pairs per run observed one process each. Cold and warm RSS differences were inside their respective 322,311-byte and 273,667-byte local allowances. macOS unique/proportional memory and allocation counts remain unqualified.

The [compact observations](data/merged-macos-url-django-20260925.json) contain all 64 timed and memory attempt results, the paired ratios, build identities, input lock, exact benchmark command template, and controller resources. Each run used the standard profile: five alternating timing pairs followed by three alternating external memory pairs. Cold wall timing covers spawn to exit for one first request; warm wall timing covers the request interval inside each process. Kernel `wait4` user plus system time covers the workload root. The four serial controller commands consumed **52.01 user plus system CPU seconds** including children; their maximum reported RSS was **79,642,624 bytes**, with zero swaps. The host was an Apple M1 Pro running macOS 26.5.2. The local run did not deny network, and neither Django task requires it.

The wheels were fetched into the persistent experiment worktree and reverified against their approved lock. The host Python 3.13 default CA path failed the first fetch; retrying with `/etc/ssl/cert.pem` succeeded. The four harness baseline snapshots and ignored result trees are generated artifacts, not experiment evidence. The checked-in compact observations and the source, build recipe, and workload code are sufficient to repeat this comparison.
