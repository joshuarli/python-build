{
  description = "Experimental Nix-pinned, Alpine/musl-equivalent Linux CPython builders";

  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-26.05/nixexprs.tar.xz";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
    in
    {
      packages = nixpkgs.lib.genAttrs systems (system:
        import ./nix/bootstrap.nix { pkgs = nixpkgs.legacyPackages.${system}; }
      );
    };
}
