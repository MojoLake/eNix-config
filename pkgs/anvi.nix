{
    lib,
    stdenv,
    fetchFromGitHub,
    meson,
    ninja,
    pkg-config,
    wayland-scanner,
    wayland,
    wayland-protocols,
    libxkbcommon,
    cairo,
    pango,
    libgrapheme,
    gtk4,
    glib,
    wrapGAppsHook4,
}:

stdenv.mkDerivation {
    pname = "anvi";
    version = "0.1.0";

    src = fetchFromGitHub {
        owner = "MojoLake";
        repo = "anvi";
        rev = "40f2b3413e0b17cff0f85d91062a7b7cc70d0c88";
        hash = "sha256-54o1aeYkaDT8EL61fBI7LHSlmmnO6XgP6VYsDo8d4+s=";
    };

    nativeBuildInputs = [
        meson
        ninja
        pkg-config
        wayland-scanner
        wrapGAppsHook4
    ];

    buildInputs = [
        wayland
        wayland-protocols
        libxkbcommon
        cairo
        pango
        libgrapheme
        gtk4
        glib
    ];

    doCheck = true;
}
