{
  description = "MojoLake's NixOS conf";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    elephant.url = "github:abenz1267/elephant";

    wifi-manager.url = "github:Vijay-papanaboina/wifi-manager";

    walker = {
      url = "github:abenz1267/walker";
      inputs.elephant.follows = "elephant";
    };
  };

  outputs = { nixpkgs, nixpkgs-unstable, home-manager, walker, wifi-manager, ... }:
  let
    mkUnstablePkgs = system: import nixpkgs-unstable {
      inherit system;
      config.allowUnfree = true;
    };

    # Standalone Home Manager config: ./home/common.nix plus per-machine modules.
    mkHome = { system, username, homeDirectory, modules, extraSpecialArgs ? { } }:
      home-manager.lib.homeManagerConfiguration {
        pkgs = nixpkgs.legacyPackages.${system};
        extraSpecialArgs = {
          unstablePkgs = mkUnstablePkgs system;
        } // extraSpecialArgs;

        modules = [
          ./home/common.nix
          { home = { inherit username homeDirectory; }; }
        ] ++ modules;
      };
  in
  {
    nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        ./configuration.nix
      ];
    };

    # NixOS laptop
    homeConfigurations."mojolake" = mkHome {
      system = "x86_64-linux";
      username = "mojolake";
      homeDirectory = "/home/mojolake";
      extraSpecialArgs = {
        wifiManager = wifi-manager.packages.x86_64-linux.default.overrideAttrs (old: {
          patches = (old.patches or []) ++ [
            ./patches/wifi-manager-audio-callback.patch
            ./patches/wifi-manager-refresh-backpressure.patch
          ];
          nativeCheckInputs = (old.nativeCheckInputs or []) ++ [ nixpkgs.legacyPackages.x86_64-linux.dbus ];
        });
      };
      modules = [
        walker.homeManagerModules.default
        ./home/linux.nix
      ];
    };

    # Work MacBook (Verda)
    homeConfigurations."eliassimojoki" = mkHome {
      system = "aarch64-darwin";
      username = "eliassimojoki";
      homeDirectory = "/Users/eliassimojoki";
      modules = [
        ./home/darwin.nix
      ];
    };
  };
}
