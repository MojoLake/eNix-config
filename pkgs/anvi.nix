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
        rev = "241af9a74fb54fad74bf031f6afb8cc0eb17a90b";
        hash = "sha256-tHK885PVuFq8E3/zzjWcksX4MpWD7wAsBeiY8Pi/OAY=";
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
