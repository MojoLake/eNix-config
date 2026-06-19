{ config, pkgs, ... }:

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
  home.packages = [
    # # Adds the 'hello' command to your environment. It prints a friendly
    # # "Hello, world!" when run.
    pkgs.hello
    
    pkgs.zip
    pkgs.unzip

    pkgs.neovim

    pkgs.gcc
    pkgs.gnumake

    pkgs.python3

    pkgs.brightnessctl

    pkgs.wtype

    pkgs.usbutils
    pkgs.v4l-utils

    pkgs.jq

    # # It is sometimes useful to fine-tune packages, for example, by applying
    # # overrides. You can do that directly here, just don't forget the
    # # parentheses. Maybe you want to install Nerd Fonts with a limited number of
    # # fonts?
    # (pkgs.nerdfonts.override { fonts = [ "FantasqueSansMono" ]; })

    # # You can also create simple shell scripts directly inside your
    # # configuration. For example, this adds a command 'my-hello' to your
    # # environment:
    # (pkgs.writeShellScriptBin "my-hello" ''
    #   echo "Hello, ${config.home.username}!"
    # '')
  ];

  # Home Manager is pretty good at managing dotfiles. The primary way to manage
  # plain files is through 'home.file'.
  home.file = {
    # # Building this configuration will create a copy of 'dotfiles/screenrc' in
    # # the Nix store. Activating the configuration will then make '~/.screenrc' a
    # # symlink to the Nix store copy.
    # ".screenrc".source = dotfiles/screenrc;

    # # You can also set the file content immediately.
    # ".gradle/gradle.properties".text = ''
    #   org.gradle.console=verbose
    #   org.gradle.daemon.idletimeout=3600000
    # '';
  };

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

  # <3 hashimoto
  programs.ghostty = {
    enable = true;

    settings = {
      keybind = [
 	"ctrl+w=close_tab"
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
      };
    };
  };

  # configure neovim through the lua config
  xdg.configFile."nvim".source =
  	config.lib.file.mkOutOfStoreSymlink
		"${config.home.homeDirectory}/eNix-config/dotfiles/nvim";

  programs.ripgrep.enable = true;
  programs.fd.enable = true;

  programs.zsh = {
    enable = true;
    enableCompletion = true;
    autosuggestion.enable = true;
    syntaxHighlighting.enable = true;
    defaultKeymap = "viins";

    shellAliases = {
      rebuild-all = "sudo nixos-rebuild switch --flake ~/eNix-config#nixos && home-manager switch --flake ~/eNix-config#mojolake";
      vi = "nvim";
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

  # allow unfree packages
  nixpkgs.config.allowUnfree = true;
  programs.obsidian.enable = true;
}
