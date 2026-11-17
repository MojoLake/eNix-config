{ config, lib, pkgs, ... }:
let
  python = pkgs.python3.withPackages (ps: [ ps.tomlkit ]);
  source = ../scripts/agent-notify;
  command = "${config.home.homeDirectory}/.local/bin/agent-notify";
  codexSettings = pkgs.writeText "agent-notify-codex-settings.json"
    (builtins.toJSON config.programs.codex.settings);
in
{
  # The desktop app updates this file itself. Merge the declared settings at
  # activation instead of replacing the user's writable config with a symlink.
  # The Codex package wrapper currently makes HM choose config.yaml; disable
  # both names so a future package version change cannot overwrite config.toml.
  home.file.".codex/config.toml".enable = false;
  home.file.".codex/config.yaml".enable = false;

  home.file.".local/bin/agent-notify" = {
    executable = true;
    text = ''
      #!${pkgs.runtimeShell}
      exec ${python}/bin/python3 ${source}/notify.py "$@"
    '';
  };
  home.file.".pi/agent/extensions/agent-notify.ts".text =
    builtins.replaceStrings [ "@NOTIFY_COMMAND@" ] [ command ]
      (builtins.readFile (source + /pi.ts));

  home.activation.agentNotifications = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
    run ${python}/bin/python3 ${source}/configure.py \
      --home ${lib.escapeShellArg config.home.homeDirectory} \
      --command ${lib.escapeShellArg command} \
      --codex-settings ${codexSettings}
  '';
}
