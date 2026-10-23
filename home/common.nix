# Home Manager config shared by the NixOS laptop and the work MacBook.
# Platform-specific parts live in ./linux.nix and ./darwin.nix.
{ config, pkgs, unstablePkgs, ... }:

let
  # Stable Anki needs a QtWebEngine that isn't cached and fails to build on macOS,
  # so the Mac uses unstable. There, anki-mac-helper declares version 26.08 but its
  # metadata says 0.1.1, which fails nixpkgs' metadata check; skip that check.
  ankiPkgs =
    if pkgs.stdenv.isDarwin then
      unstablePkgs.extend (final: prev: {
        pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
          (pyFinal: pyPrev: {
            anki-mac-helper = pyPrev.anki-mac-helper.overridePythonAttrs {
              dontCheckPythonMetadata = true;
            };
          })
        ];
      })
    else
      pkgs;

  ankiWithConnect = ankiPkgs.anki.withAddons [
    ankiPkgs.ankiAddons.anki-connect
  ];

  # nixpkgs' Anki has no .app on macOS; add a small bundle so it shows up in
  # Spotlight via ~/Applications/Home Manager Apps.
  ankiDesktop =
    if pkgs.stdenv.isDarwin then ankiApp else ankiWithConnect;

  ankiApp = pkgs.runCommand "anki-app" { nativeBuildInputs = [ pkgs.libicns ]; } ''
    mkdir -p $out
    ln -s ${ankiWithConnect}/bin $out/bin
    app=$out/Applications/Anki.app/Contents
    mkdir -p $app/MacOS $app/Resources
    png2icns $app/Resources/anki.icns \
      ${ankiWithConnect}/share/icons/hicolor/128x128/apps/anki.png
    cat > $app/MacOS/Anki <<EOF
    #!/bin/sh
    exec ${ankiWithConnect}/bin/anki "\$@"
    EOF
    chmod +x $app/MacOS/Anki
    cat > $app/Info.plist <<EOF
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
      <key>CFBundleName</key><string>Anki</string>
      <key>CFBundleDisplayName</key><string>Anki</string>
      <key>CFBundleIdentifier</key><string>net.ankiweb.dtop.nix</string>
      <key>CFBundleExecutable</key><string>Anki</string>
      <key>CFBundleIconFile</key><string>anki</string>
      <key>CFBundlePackageType</key><string>APPL</string>
      <key>CFBundleShortVersionString</key><string>${ankiWithConnect.version or "0"}</string>
      <key>NSHighResolutionCapable</key><true/>
    </dict>
    </plist>
    EOF
  '';

  ankiCard = ankiPkgs.writeShellApplication {
    name = "anki-card";
    text = ''
      export PYTHONPATH="${ankiPkgs.anki.lib}/${ankiPkgs.python3.sitePackages}"
      exec ${ankiPkgs.python3}/bin/python3 ${../scripts/anki-card.py} "$@"
    '';
  };
in
{
  # home.username and home.homeDirectory are set per machine in flake.nix.

  # This value determines the Home Manager release that your configuration is
  # compatible with. This helps avoid breakage when a new Home Manager release
  # introduces backwards incompatible changes.
  #
  # You should not change this value, even if you update Home Manager. If you do
  # want to update the value, then make sure to first check the Home Manager
  # release notes.
  home.stateVersion = "26.05"; # Please read the comment before changing.

  # The home.packages option allows you to install Nix packages into your
  # environment.
  home.packages = with pkgs; [
    # # Adds the 'hello' command to your environment. It prints a friendly
    # # "Hello, world!" when run.
    hello

    zip
    unzip

    typst

    gnumake
    meson
    clang-tools

    zig
    zls

    rustup

    python3
    basedpyright
    uv

    scala_2_12

    nerd-fonts.symbols-only

    jq

    tree

    kubectl
    k9s

    ankiDesktop
    ankiCard

    unstablePkgs.spotify-player

    # Pi coding agent (pi.dev); stable lags well behind upstream.
    unstablePkgs.pi-coding-agent

    nodejs_24
    yarn
  ];

  # Codex reads ~/.agents/skills and Claude Code reads ~/.claude/skills;
  # both get the same skills from the repo.
  home.file = {
    ".agents/skills/anki-cards".source = ../skills/anki-cards;
    ".agents/skills/paper-to-kindle".source = ../skills/paper-to-kindle;
    ".claude/skills/anki-cards".source = ../skills/anki-cards;
    ".claude/skills/paper-to-kindle".source = ../skills/paper-to-kindle;
  };

  home.sessionPath = [
    "$HOME/.local/bin"
  ];

  home.sessionVariables = {
    EDITOR = "nvim";
    VISUAL = "nvim";
  };

  # Let Home Manager install and manage itself.
  programs.home-manager.enable = true;

  programs.codex = {
    enable = true;
    # Trust the launch directory without writing to the Home Manager-owned config.
    package = pkgs.writeShellScriptBin "codex" ''
      trusted_path=$(${pkgs.jq}/bin/jq -rn --arg path "$PWD" '$path | tojson')
      exec ${unstablePkgs.codex}/bin/codex \
        -c "projects={$trusted_path={trust_level=\"trusted\"}}" \
        "$@"
    '';

    settings = {
      projects.${config.home.homeDirectory}.trust_level = "trusted";
    };
  };

  # <3 hashimoto
  programs.ghostty = {
    enable = true;

    settings = {
      working-directory = "home";
      window-inherit-working-directory = true;
    };
  };

  # to flex on other people
  programs.fastfetch.enable = true;

  programs.git = {
    enable = true;

    settings = {
      user = {
        name = "Elias Simojoki";
        email = "simo.simojoki@gmail.com";
      };

      init.defaultBranch = "main";

      alias = {
        st = "status";
        br = "branch";
        c = "commit";
      };
    };
  };

  programs.neovim = {
    enable = true;
    defaultEditor = true;
    sideloadInitLua = true;
    viAlias = true;
    vimAlias = true;
  };

  # configure neovim through the lua config
  xdg.configFile."nvim".source =
    config.lib.file.mkOutOfStoreSymlink
      "${config.home.homeDirectory}/eNix-config/dotfiles/nvim";

  programs.ripgrep.enable = true;
  programs.fd.enable = true;

  programs.fzf = {
    enable = true;
    enableZshIntegration = true;
  };

  programs.zsh = {
    enable = true;
    enableCompletion = true;
    autosuggestion.enable = true;
    syntaxHighlighting.enable = true;
    defaultKeymap = "viins";

    plugins = [
      {
        name = "fzf-tab";
        src = pkgs.zsh-fzf-tab;
        file = "share/fzf-tab/fzf-tab.plugin.zsh";
      }
    ];

    shellAliases = {
      com = "g++ -Wall -fsanitize=address";
      vi = "nvim";
      codex-d = "codex --dangerously-bypass-approvals-and-sandbox";
      nd = "nix develop --command zsh -i";
    };

    initContent = ''
      bindkey -M viins '^L' autosuggest-accept
    '';
  };

  # allow unfree packages
  nixpkgs.config.allowUnfree = true;
  programs.obsidian.enable = true;
}
