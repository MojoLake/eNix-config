{ config, pkgs, unstablePkgs, ... }:

let
  kindleMail = pkgs.writeShellApplication {
    name = "kindle-mail";
    runtimeInputs = [
      pkgs.libsecret
      pkgs.python3
    ];
    text = ''
      exec ${pkgs.python3}/bin/python3 ${./scripts/kindle-mail.py} "$@"
    '';
  };
in
{
  # Home Manager needs a bit of information about you and the paths it should
  # manage.
  home.username = "mojolake";
  home.homeDirectory = "/home/mojolake";

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

    gcc
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

    brightnessctl

    wtype
    swaybg
    wayland-scanner

    usbutils
    v4l-utils

    jq

    kindleMail

    tree

    # For screenshots to clipboard
    grim
    slurp
    wl-clipboard

    # For screen recording
    gpu-screen-recorder
    ffmpeg-headless
    libnotify
    glib

    pciutils

    thunderbird

    xdg-utils

    imv
    snapshot
    zathura
    mpv
    unstablePkgs.spotify-player
    playerctl

    thunar
    tumbler

    nodejs_24
    yarn

    # # It is sometimes useful to fine-tune packages, for example, by applying
    # # overrides. You can do that directly here, just don't forget the
    # # parentheses. Maybe you want to install Nerd Fonts with a limited number of
    # # fonts?
    # (nerdfonts.override { fonts = [ "FantasqueSansMono" ]; })

    # # You can also create simple shell scripts directly inside your
    # # configuration. For example, this adds a command 'my-hello' to your
    # # environment:
    # (writeShellScriptBin "my-hello" ''
    #   echo "Hello, ${config.home.username}!"
    # '')
  ];

  # Home Manager is pretty good at managing dotfiles. The primary way to manage
  # plain files is through 'home.file'.
  home.file = {
    ".agents/skills/anki-cards".source = ./skills/anki-cards;
    ".agents/skills/paper-to-kindle".source = ./skills/paper-to-kindle;

    # # Building this configuration will create a copy of 'dotfiles/screenrc' in
    # # the Nix store. Activating the configuration will then make '~/.screenrc' a
    # # symlink to the Nix store copy.
    # ".screenrc".source = dotfiles/screenrc;

    # # You can also set the file content immediately.
    # ".gradle/gradle.properties".text = ''
    #   org.gradle.console=verbose
    #   org.gradle.daemon.idletimeout=3600000
    # '';

    ".local/bin/gpu-screen-recorder-toggle" = {
        source = ./scripts/gpu-screen-recorder-toggle;
        executable = true;
    };

    ".local/bin/gpu-screen-recorder-recent" = {
        source = ./scripts/gpu-screen-recorder-recent;
        executable = true;
    };

    ".local/bin/touchpad-toggle" = {
        source = ./scripts/touchpad-toggle;
        executable = true;
    };
  };

  home.sessionPath = [
    "$HOME/.local/bin"
  ];

  # Home Manager can also manage your environment variables through
  # 'home.sessionVariables'. These will be explicitly sourced when using a
  # shell provided by Home Manager. If you don't want to manage your shell
  # through Home Manager then you have to manually source 'hm-session-vars.sh'
  # located at either
  #
  #  ~/.nix-profile/etc/profile.d/hm-session-vars.sh
  #
  # or
  #
  #  ~/.local/state/nix/profiles/profile/etc/profile.d/hm-session-vars.sh
  #
  # or
  #
  #  /etc/profiles/per-user/mojolake/etc/profile.d/hm-session-vars.sh
  #
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
      mcp_servers.kindle_mail = {
        command = "${kindleMail}/bin/kindle-mail";
        args = [ "mcp" ];
        enabled = true;
        required = false;
        enabled_tools = [
          "check_kindle_mail_setup"
          "preview_kindle_delivery"
          "send_to_kindle"
        ];
        default_tools_approval_mode = "writes";

        tools.send_to_kindle.approval_mode = "prompt";
      };

      projects."/home/mojolake".trust_level = "trusted";
    };
  };

  # <3 hashimoto
  programs.ghostty = {
    enable = true;
    systemd.enable = true;

    settings = {
      gtk-single-instance = true;
      working-directory = "home";
      window-inherit-working-directory = true;

      keybind = [
      ];
    };
  };

  # to flex on other people
  programs.fastfetch.enable = true;

  # not to flex on other people
  programs.firefox.enable = true;

  # macos spotlight but for linux
  programs.walker = {
    enable = true;
    runAsService = true;

    config.keybinds = {
      next = [ "Down" "ctrl j" ];
      previous = [ "Up" "ctrl k" ];
    };
    
    elephant.providers = [
      "desktopapplications"
      "calc"
      "files"
      "niriactions"
      "windows"
    ];
  };

  # programs.swaylockenable = true;
  programs.swaylock = {
    enable = true;
    
    settings = {
      color = "041a1f";
      image = ./images/dark-sand.jpg;
      scaling = "fill";
    };
  };

  services.mako = {
    enable = true;

    settings."app-name=batsignal" = {
      background-color = "#991b1b";
      border-color = "#ef4444";
      text-color = "#ffffff";
    };

    settings."app-name=\"Screen Recorder\" actionable" = {
      max-icon-size = 160;
      on-button-middle = ''exec makoctl menu -n "$id" -- walker --dmenu --placeholder "Recording action"'';
    };
  };

  services.batsignal = {
    enable = true;
    extraArgs = [
      "-w" "10"
      "-c" "5"
      "-d" "0"
    ];
  };

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
      rebuild-all = "sudo nixos-rebuild switch --flake ~/eNix-config#nixos && home-manager switch --flake ~/eNix-config#mojolake";
      vi = "nvim";
      open = "xdg-open";
      codex-d = "codex --dangerously-bypass-approvals-and-sandbox";
      nd = "nix develop --command zsh -i";
    };
    
    initContent = ''
	bindkey -M viins '^L' autosuggest-accept
    '';

  };


  # configure niri through its own config file
  xdg.configFile."niri/config.kdl" = {
    source = ./dotfiles/niri/config.kdl;
    force = true;
  };

  xdg.configFile."systemd/user/graphical-session.target.wants/app-com.mitchellh.ghostty.service".source =
    "${config.programs.ghostty.package}/share/systemd/user/app-com.mitchellh.ghostty.service";

  xdg.configFile."waybar/config.jsonc" = {
    source = ./dotfiles/waybar/config.jsonc;
    force = true;
    onChange = "${pkgs.systemd}/bin/systemctl --user try-restart waybar.service";
  };
  xdg.configFile."waybar/style.css" = {
    source = ./dotfiles/waybar/style.css;
    force = true;
  };

  xdg.configFile."mpv/mpv.conf" = {
    source = ./dotfiles/mpv/mpv.conf;
  };


  # allow unfree packages
  nixpkgs.config.allowUnfree = true;
  programs.obsidian.enable = true;

    xdg.mimeApps = {
        enable = true;

        defaultApplications = {
          "image/png" = [ "imv.desktop" ];
          "image/jpeg" = [ "imv.desktop" ];
          "image/webp" = [ "imv.desktop" ];

          "application/pdf" = [ "org.pwmt.zathura.desktop" ];

          "inode/directory" = [ "thunar.desktop" ];

            "video/mp4" = [ "mpv.desktop" ];
            "video/x-matroska" = [ "mpv.desktop" ]; # .mkv
            "video/webm" = [ "mpv.desktop" ];
            "video/x-msvideo" = [ "mpv.desktop" ]; # .avi
        };
    };
}
