return {
  "windwp/nvim-ts-autotag",
  event = "InsertEnter",
  config = function()
    require("nvim-ts-autotag").setup({
      per_filetype = {
        rust = {
          enable_close = false,
          enable_rename = false,
          enable_close_on_slash = false,
        },
      },
    })
  end,
}
