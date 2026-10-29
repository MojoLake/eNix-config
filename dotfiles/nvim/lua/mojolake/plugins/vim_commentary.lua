return {
    {
        "numToStr/Comment.nvim",
        opts = {

        },
        config = function()
            require('Comment').setup({
                pre_hook = function(ctx)
                    -- Comment.nvim assumes get_parser throws when no parser exists.
                    -- Neovim 0.12 returns nil; use Python's commentstring directly.
                    if vim.bo.filetype == 'python'
                        and ctx.ctype == require('Comment.utils').ctype.linewise then
                        return vim.bo.commentstring
                    end
                end,
            })
        end,
        lazy = false,
    }
}
