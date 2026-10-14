# Home Manager config for the work MacBook. Shared config lives in ./common.nix.
#
# Nix itself is the upstream install; /etc/nix/nix.conf is left alone because
# Aikido Endpoint Protection adds its ssl-cert-file there.
{ config, pkgs, unstablePkgs, ... }:

{
  # Enable flakes for this user without touching the system nix.conf.
  xdg.configFile."nix/nix.conf".text = ''
    experimental-features = nix-command flakes
  '';

  home.packages = [
    # Stable ols pulls in an LLVM 18 that isn't cached and fails to build on macOS.
    unstablePkgs.ols

    # Tiling window manager; not in stable nixpkgs yet.
    unstablePkgs.omniwm
  ];

  # Linked to the repo copy so changes made in OmniWM's settings window land in git.
  xdg.configFile."omniwm/settings.toml".source =
    config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/eNix-config/dotfiles/omniwm/settings.toml";

  # Swallow Cmd+H (hide app) everywhere; it's too easy to hit instead of OmniWM's Option+H.
  services.skhd = {
    enable = true;
    config = ''
      cmd - h : true
    '';
  };

  # nixpkgs builds Ghostty from source only on Linux; use the upstream app on macOS.
  programs.ghostty.package = pkgs.ghostty-bin;

  # Repos under ~/work/ commit with the Verda email.
  programs.git.includes = [
    {
      condition = "gitdir:~/work/";
      contents.user.email = "elias.simojoki@verda.com";
    }
  ];

  programs.zsh.shellAliases = {
    hms = "home-manager switch --flake ~/eNix-config#eliassimojoki";
  };
}
