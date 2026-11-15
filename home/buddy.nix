{ config, pkgs, ... }:
{
  home.packages = [ pkgs.python3 ];
  home.file.".local/bin/buddy".source = config.lib.file.mkOutOfStoreSymlink
    "${config.home.homeDirectory}/eNix-config/scripts/buddy/buddy";

  # Check deadlines outside the terminal; generate one question when a check-in is due.
  launchd.agents.buddy = {
    enable = true;
    config = {
      ProgramArguments = [ "${config.home.homeDirectory}/.local/bin/buddy" "worker" ];
      RunAtLoad = true;
      StartInterval = 30;
      ProcessType = "Background";
      StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/buddy.log";
    };
  };
}
