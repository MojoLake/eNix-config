return {
      "nvim-treesitter/nvim-treesitter",
      build = ":TSUpdate",
      event = { "BufReadPost", "BufNewFile" },
      config = function()
        require("nvim-treesitter.configs").setup({
          ensure_installed = { "c", "cpp", "javascript", "typescript", "tsx", "html", "css", "lua", "zig", },
          highlight = { enable = true },
          indent = { enable = true },
        })
      end,
--     nvim-ts-auto
-- tag').setup()
}
