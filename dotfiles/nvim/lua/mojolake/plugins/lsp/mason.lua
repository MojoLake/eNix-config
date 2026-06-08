-- return {}
return {
    "williamboman/mason.nvim",
    dependencies = {
        "williamboman/mason-lspconfig.nvim",
    },
    config = function()
        local mason = require("mason")

        local mason_lspconfig = require("mason-lspconfig")

        mason.setup({})

        mason_lspconfig.setup({
            ensure_installed = {
                "jdtls",
                "basedpyright",
                "rust_analyzer",
                "lua_ls",
                "zls",
                "tinymist",
            },
            automatic_installation = true,
        })

    end,
}
