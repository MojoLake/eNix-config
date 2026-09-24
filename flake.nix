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
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
    unstablePkgs = import nixpkgs-unstable {
      inherit system;
      config.allowUnfree = true;
    };
  in
  {
    nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
      # system = "x86_64-linux";
      inherit system;
      modules = [
        ./configuration.nix
      ];
    };

    homeConfigurations."mojolake" = home-manager.lib.homeManagerConfiguration {
      inherit pkgs;
      extraSpecialArgs = {
        inherit unstablePkgs;
        wifiManager = wifi-manager.packages.${system}.default.overrideAttrs (old: {
          patches = (old.patches or []) ++ [ ./patches/wifi-manager-audio-callback.patch ];
        });
      };
      
      modules = [
	walker.homeManagerModules.default
	./home.nix
      ];
    };
  };
}
