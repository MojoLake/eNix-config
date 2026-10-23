# Home Manager config for the work MacBook. Shared config lives in ./common.nix.
#
# Nix itself is the upstream install; /etc/nix/nix.conf is left alone because
# Aikido Endpoint Protection adds its ssl-cert-file there.
{ config, pkgs, unstablePkgs, ... }:
let
  # Keep the upstream signed app intact for macOS Accessibility permissions.
  hammerspoon = pkgs.stdenvNoCC.mkDerivation {
    pname = "hammerspoon";
    version = "1.1.1";
    src = pkgs.fetchurl {
      url = "https://github.com/Hammerspoon/hammerspoon/releases/download/1.1.1/Hammerspoon-1.1.1.zip";
      sha256 = "11bb1c90faf5427f37c7bd4fe7eab9774ae43e1d5cb020c5b3088dac32849efa";
    };
    nativeBuildInputs = [ pkgs.unzip ];
    sourceRoot = ".";
    dontBuild = true;
    dontFixup = true;
    installPhase = ''
      mkdir -p "$out/Applications"
      cp -R Hammerspoon.app "$out/Applications/"
    '';
  };
in
{
  imports = [ ./focusguard.nix ];

  # Enable flakes for this user without touching the system nix.conf.
  xdg.configFile."nix/nix.conf".text = ''
    experimental-features = nix-command flakes
  '';

  home.packages = [
    # Stable ols pulls in an LLVM 18 that isn't cached and fails to build on macOS.
    unstablePkgs.ols

    # Tiling window manager; not in stable nixpkgs yet.
    unstablePkgs.omniwm
    hammerspoon
  ];

  # Desktop modifier exceptions; the Command/Option swap remains in macOS settings.
  home.file.".hammerspoon/init.lua".source =
    config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/eNix-config/dotfiles/hammerspoon/init.lua";
  launchd.agents.hammerspoon = {
    enable = true;
    config = {
      # Launch the installed copy: this is the path approved in macOS privacy settings.
      ProgramArguments = [ "/usr/bin/open" "-g" "${config.home.homeDirectory}/Applications/Home Manager Apps/Hammerspoon.app" ];
      RunAtLoad = true;
      ProcessType = "Interactive";
    };
  };

  # Linked to the repo copy so changes made in OmniWM's settings window land in git.
  xdg.configFile."omniwm/settings.toml".source =
    config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/eNix-config/dotfiles/omniwm/settings.toml";

  # nixpkgs builds Ghostty from source only on Linux; use the upstream app on macOS.
  programs.ghostty.package = pkgs.ghostty-bin;

  # Repos under ~/work/ commit with the Verda email.
  programs.git.includes = [
    {
      condition = "gitdir:~/work/";
      contents.user.email = "elias.simojoki@verda.com";
    }
  ];

  # Pi: Verda's internal inference gateway (VPN required). The key lives in a
  # user-only file outside the store; pi runs the `!` command to read it.
  home.file.".pi/agent/models.json".text = builtins.toJSON {
    providers.verda = {
      name = "Verda";
      baseUrl = "https://inference.verda.com/v1";
      api = "openai-completions";
      apiKey = "!cat ${config.home.homeDirectory}/.config/verda/inference-api-key";
      authHeader = true;
      compat.supportsDeveloperRole = false;
      models = [
        {
          id = "kimi-k3";
          name = "Kimi K3 (Verda)";
          # Returns reasoning_content alongside the answer.
          reasoning = true;
          input = [ "text" ];
          # The gateway rejects max_tokens above 1048576.
          contextWindow = 1048576;
          # Leave room for reasoning tokens, which share the output budget.
          maxTokens = 32768;
          cost = { input = 0; output = 0; cacheRead = 0; cacheWrite = 0; };
        }
      ];
    };
  };

  programs.zsh.shellAliases = {
    hms = "home-manager switch --flake ~/eNix-config#eliassimojoki";
  };
}
