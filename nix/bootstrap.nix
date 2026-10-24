# Native-host Nix derivations produce the exact Docker contexts used by the
# existing Alpine/musl toolchain. Nixpkgs supplies only fetch/copy tools; no
# Nixpkgs libc, compiler, linker, or Rust runtime enters the target image.
{ pkgs }:
let
  baseLock = builtins.fromJSON (builtins.readFile ../bootstrap.lock.json);
  targets = {
    amd64 = {
      machine = "x86_64";
      experimentalLock = ../research/rtls-graviola/linux-bootstrap-x86_64.json;
    };
    arm64 = {
      machine = "aarch64";
      experimentalLock = ../research/rtls-graviola/linux-bootstrap.lock.json;
    };
  };

  fetched = item: name: pkgs.fetchurl {
    inherit name;
    inherit (item) url sha256;
  };

  apkCopies = items: outputDir:
    builtins.concatStringsSep "\n" (map (item:
      let name = "${item.sha256}.apk";
      in ''cp ${fetched item name} "$out/${outputDir}/${name}"''
    ) items);

  rustCopies = items: outputDir:
    builtins.concatStringsSep "\n" (map (item:
      ''cp ${fetched item item.file} "$out/${outputDir}/${item.file}"''
    ) items);

  baseContext = arch:
    let
      target = targets.${arch};
      packages = baseLock.linux_toolchain.apk_closure.${target.machine};
    in
    pkgs.runCommand "python-build-nix-base-${arch}-context" { } ''
      set -eu
      mkdir -p "$out/buildsys" "$out/.cache/bootstrap/apk/${arch}"
      cp ${../Dockerfile} "$out/Dockerfile"
      cp ${../bootstrap.lock.json} "$out/bootstrap.lock.json"
      cp ${../buildsys/targets.py} "$out/buildsys/targets.py"
      : > "$out/.dockerignore"
      ${apkCopies packages ".cache/bootstrap/apk/${arch}"}
    '';

  overlayContext = arch:
    let
      target = targets.${arch};
      lock = builtins.fromJSON (builtins.readFile target.experimentalLock);
    in
    assert lock.target.architecture == target.machine;
    pkgs.runCommand "python-build-nix-rtls-${arch}-context" { } ''
      set -eu
      mkdir -p "$out/research/rtls-graviola" \
        "$out/.cache/bootstrap/rtls-linux/apk" \
        "$out/.cache/bootstrap/rtls-linux/rust"
      cp ${../research/rtls-graviola/Dockerfile.linux} "$out/Dockerfile.linux"
      cp ${../bootstrap.lock.json} "$out/bootstrap.lock.json"
      cp ${target.experimentalLock} "$out/research/rtls-graviola/linux-bootstrap.lock.json"
      : > "$out/.dockerignore"
      ${apkCopies lock.apk_closure ".cache/bootstrap/rtls-linux/apk"}
      ${rustCopies lock.rust.components ".cache/bootstrap/rtls-linux/rust"}
    '';
in
{
  base-amd64 = baseContext "amd64";
  base-arm64 = baseContext "arm64";
  rtls-amd64 = overlayContext "amd64";
  rtls-arm64 = overlayContext "arm64";
}
