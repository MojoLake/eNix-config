{
  description = "MojoLake's NixOS conf";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    elephant.url = "github:abenz1267/elephant";

    walker = {
      url = "github:abenz1267/walker";
      inputs.elephant.follows = "elephant";
    };
  };

  outputs = { nixpkgs, home-manager, walker, ... }: 
  let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
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
      
      modules = [
	walker.homeManagerModules.default
	.home.nix
      ];
    };
  };
}
