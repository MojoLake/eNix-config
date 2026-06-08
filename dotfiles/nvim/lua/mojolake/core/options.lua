vim.opt.mouse = "a"
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.title = true

vim.opt.expandtab = true
vim.opt.shiftwidth = 4
vim.opt.tabstop = 4
vim.opt.signcolumn = "yes:1"
vim.opt.cursorline = true
vim.opt.undofile = true

vim.opt.undodir = os.getenv("HOME") .. "/.local/share/nvim/undo"

vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- Enable true color support
vim.opt.termguicolors = true

-- Needed so that node --watch works properly: https://github.com/nodejs/node/issues/22517 --
vim.opt.writebackup = false

vim.g.vimtex_view_method = 'zathura'
vim.g.vimtex_quickfix_autoclose_after_keystrokes = 1
vim.g.vimtex_quickfix_ignore_filters = {'Underfull','Overfull'}

vim.api.nvim_set_keymap('n', '<leader>rs', ':!scala3 %<CR>', { noremap = true, silent = true })

local userconfig_group = vim.api.nvim_create_augroup('userconfig', { clear = true })
vim.api.nvim_create_autocmd({'BufWinEnter'}, {
  group = 'userconfig',
  desc = 'return cursor to where it was last time closing the file',
  pattern = '*',
  command = 'silent! normal! g`"zv',
})

vim.api.nvim_create_autocmd("FileType", {
    pattern = { "javascriptreact", "typescriptreact", "javascript", "typescript" },
    callback = function()
        vim.opt.shiftwidth = 2
        vim.opt.tabstop = 2
        vim.opt.softtabstop = 2
    end,
})
