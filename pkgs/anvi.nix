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
        rev = "9060e487686530523cb0f4d15930325865ed2ee3";
        hash = "sha256-+mk/MGDzfh6B6n4G1cPuPvNbnvj2BiNJErg0rN60pgc=";
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
