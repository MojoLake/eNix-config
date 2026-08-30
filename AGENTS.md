# Repository Agent Instructions

## Editing Scope

- Default to read-only work. Do not create, modify, move, or delete files unless the user explicitly asks for an implementation or other change.
- Once the user has explicitly requested a change, make all file edits reasonably required to complete that request without asking for permission for each individual file. Keep those edits within the requested scope.
- Do not commit changes or activate configurations unless the user explicitly asks for that action.

## Home Manager Commands

Run these commands from the repository root.

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
