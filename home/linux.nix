# Home Manager config for the NixOS laptop: niri desktop, Wayland tools and
# Linux-only services. Shared config lives in ./common.nix.
{ config, pkgs, wifiManager, ... }:

let
  kindleMail = pkgs.writeShellApplication {
    name = "kindle-mail";
    runtimeInputs = [
      pkgs.libsecret
      pkgs.python3
    ];
    text = ''
      exec ${pkgs.python3}/bin/python3 ${../scripts/kindle-mail.py} "$@"
    '';
  };
in
{
  home.packages = with pkgs; [
    gcc

    ols

    brightnessctl
    wifiManager
    adwaita-icon-theme

    wtype
    swaybg
    wayland-scanner

    usbutils
    v4l-utils

    kindleMail

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
    playerctl

    thunar
    tumbler
  ];

  home.file = {
    ".local/bin/gpu-screen-recorder-toggle" = {
        source = ../scripts/gpu-screen-recorder-toggle;
        executable = true;
    };

    ".local/bin/gpu-screen-recorder-recent" = {
        source = ../scripts/gpu-screen-recorder-recent;
        executable = true;
    };

    ".local/bin/touchpad-toggle" = {
        source = ../scripts/touchpad-toggle;
        executable = true;
    };
  };

  programs.codex.settings.mcp_servers.kindle_mail = {
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

  programs.ghostty = {
    systemd.enable = true;

    settings = {
      gtk-single-instance = true;

      keybind = [
        "ctrl+shift+a=select_all"
      ];
    };
  };

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

    elephant.provider.desktopapplications.settings.window_integration = true;

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
      image = ../images/dark-sand.jpg;
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

  programs.zsh.shellAliases = {
    rebuild-all = "sudo nixos-rebuild switch --flake ~/eNix-config#nixos && home-manager switch --flake ~/eNix-config#mojolake";
    open = "xdg-open";
  };

  fonts.fontconfig.enable = true;

  xdg.configFile."wifi-manager/config.toml" = {
    text = ''
      position = "top-right"
      margin_top = 32
      margin_right = 8
      show_on_start = false
      system_icon = "computer-symbolic"
    '';
    onChange = "${pkgs.systemd}/bin/systemctl --user try-restart wifi-manager.service";
  };

  xdg.configFile."wifi-manager/style.css" = {
    text = ''
      /* Keep quick-control icons readable against the panel's dark background. */
      .cc-quick-controls button,
      .cc-quick-controls scale value {
        color: rgba(255, 255, 255, 0.92);
      }
    '';
    onChange = "${pkgs.systemd}/bin/systemctl --user try-restart wifi-manager.service";
  };

  systemd.user.services.wifi-manager = {
    Unit = {
      Description = "Wi-Fi and Bluetooth control panel";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
    };
    Service = {
      ExecStart = "${wifiManager}/bin/wifi-manager";
      Restart = "on-failure";
      RestartSec = 3;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };

  # configure niri through its own config file
  xdg.configFile."niri/config.kdl" = {
    text = builtins.replaceStrings
      [ "@wifi-manager@" ]
      [ "${wifiManager}/bin/wifi-manager" ]
      (builtins.readFile ../dotfiles/niri/config.kdl);
    force = true;
  };

  xdg.configFile."systemd/user/graphical-session.target.wants/app-com.mitchellh.ghostty.service".source =
    "${config.programs.ghostty.package}/share/systemd/user/app-com.mitchellh.ghostty.service";

  xdg.configFile."waybar/config.jsonc" = {
    text = builtins.replaceStrings
      [ "@wifi-manager@" ]
      [ "${wifiManager}/bin/wifi-manager" ]
      (builtins.readFile ../dotfiles/waybar/config.jsonc);
    force = true;
    onChange = "${pkgs.systemd}/bin/systemctl --user try-restart waybar.service";
  };
  xdg.configFile."waybar/style.css" = {
    source = ../dotfiles/waybar/style.css;
    force = true;
  };

  xdg.configFile."mpv/mpv.conf" = {
    source = ../dotfiles/mpv/mpv.conf;
  };

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
