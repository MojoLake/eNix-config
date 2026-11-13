{ pkgs, ... }:
let
  # Change these settings, rebuild Home Manager, then run `focusguard install`.
  # The system service only reads its root-owned installed copy of this policy.
  policy = pkgs.writeText "focusguard-policy.json" (builtins.toJSON {
    passages = builtins.fromJSON (builtins.readFile ../scripts/focusguard/passages.json);
    defaultMinutes = 20;
    maxMinutes = 30;
    sites = {
      youtube = [
        "youtube.com" "www.youtube.com" "m.youtube.com" "music.youtube.com"
        "youtu.be" "www.youtu.be" "youtube-nocookie.com" "www.youtube-nocookie.com"
      ];
      linkedin = [ "linkedin.com" "www.linkedin.com" "m.linkedin.com" ];
      x = [ "x.com" "www.x.com" "mobile.x.com" "twitter.com" "www.twitter.com" "mobile.twitter.com" ];
    };
  });
  source = ../scripts/focusguard;
in
{
  home.packages = [ (pkgs.writeShellScriptBin "focusguard" ''
    set -eu
    if [ "''${1:-}" = install ]; then
      exec /bin/bash ${source}/install.sh ${source} ${policy}
    fi
    case "''${1:-}" in
      learn|progress|unlock)
        exec ${pkgs.python3}/bin/python3 ${source}/tutor/tutor.py "$@"
        ;;
      unlock-typing)
        shift
        exec /usr/bin/sudo '/Library/Application Support/FocusGuard/focusguard' unlock "$@"
        ;;
    esac
    if [ ! -x '/Library/Application Support/FocusGuard/focusguard' ]; then
      echo 'FocusGuard is not installed. Run: focusguard install' >&2
      exit 1
    fi
    exec /usr/bin/sudo '/Library/Application Support/FocusGuard/focusguard' "$@"
  '') ];
}
