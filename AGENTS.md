# Repository Agent Instructions

## Editing Scope

- Default to read-only work. Do not create, modify, move, or delete files unless the user explicitly asks for an implementation or other change.
- Once the user has explicitly requested a change, make all file edits reasonably required to complete that request without asking for permission for each individual file. Keep those edits within the requested scope.
- Do not commit changes or activate configurations unless the user explicitly asks for that action.

## Commit Messages

Use concise Conventional Commit-style messages, such as `feat: add recent screen recording actions` or `fix: restore recording indicator`. Describe the user-visible change rather than implementation details.

## Layout

- `home/common.nix`: Home Manager config shared by both machines.
- `home/linux.nix`: NixOS laptop only (niri desktop, Wayland tools, systemd services).
- `home/darwin.nix`: work MacBook only.
- `configuration.nix`, `hardware-configuration.nix`: NixOS system config.

Put new config in `home/common.nix` unless it only works on one platform.

## Home Manager Commands

Run these commands from the repository root. Use `.#mojolake` on the NixOS laptop and `.#eliassimojoki` on the MacBook.

- Build and activate the Home Manager configuration:

  ```sh
  home-manager switch --flake .#mojolake
  ```

- Build and validate it without activating it:

  ```sh
  home-manager build --flake .#mojolake
  ```

- Preview a switch without performing it:

  ```sh
  home-manager -n switch --flake .#mojolake
  ```

- First activation on the MacBook, before Home Manager is installed and flakes are enabled. `NIX_CONFIG` is needed because home-manager runs its own `nix` commands, which don't inherit command-line flags:

  ```sh
  NIX_CONFIG="experimental-features = nix-command flakes" nix run home-manager/release-26.05 -- switch --flake .#eliassimojoki -b backup
  ```

## NixOS System Commands

Run these commands from the repository root.

- Build and activate the system configuration, and make it the boot default:

  ```sh
  sudo nixos-rebuild switch --flake .#nixos
  ```

- Build and validate it without activating it or changing the boot default:

  ```sh
  nixos-rebuild build --flake .#nixos
  ```

- Show which store paths a rebuild would build or download, without building or activating anything:

  ```sh
  nixos-rebuild dry-build --flake .#nixos
  ```
