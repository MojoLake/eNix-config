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
        rev = "7afd21aba317d26beeed1a49cb76731fb79d8c8a";
        hash = "sha256-fUl5mzGZNENIuO/4DL1VHsPpvBowHcmVuoG7vy8Ui7U=";
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
