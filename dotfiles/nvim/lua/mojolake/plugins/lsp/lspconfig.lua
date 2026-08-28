-- return {}
return {
    "neovim/nvim-lspconfig",
    event = { "BufReadPre", "BufNewFile" },
    dependencies = {
        "hrsh7th/cmp-nvim-lsp",
        { "antosha417/nvim-lsp-file-operations", config = true},
    },
    config = function()

        local lspconfig = require("lspconfig")

        local cmp_nvim_lsp = require("cmp_nvim_lsp")

        local opts = { noremap = true, silent = true }

        local on_attach = function(client, bufnr)
            opts.buffer = bufnr

            opts.desc = "Show LSP references"
            vim.keymap.set("n", "gR", "<cmd>Telescope lsp_references<CR>", opts)

            opts.desc = "Go to declaration"
            vim.keymap.set("n", "gd", vim.lsp.buf.declaration, opts)

            opts.desc = "Show LSP definitions"
            vim.keymap.set("n", "gD", "<cmd>Telescope lsp_definitions<CR>", opts)

            opts.desc = "See available code actions"
            vim.keymap.set({"n", "v"}, "<leader>ca", vim.lsp.buf.code_action, opts)

            opts.desc = "Show buffer diagnostics"
            vim.keymap.set("n", "<leader>y", "<cmd>Telescope diagnostics bufnr=0<CR>", opts)

            opts.desc = "Show documentation for what is under cursor"
            vim.keymap.set("n", "<leader>boc", vim.lsp.buf.hover, opts)

            opts.desc = "Smart diagnostic/documentation viewer"
            vim.keymap.set("n", "gh", function()
                -- Check if there's already a smart popup open and close it
                if vim.g.lsp_smart_popup_win and vim.api.nvim_win_is_valid(vim.g.lsp_smart_popup_win) then
                    vim.api.nvim_win_close(vim.g.lsp_smart_popup_win, true)
                    vim.g.lsp_smart_popup_win = nil
                    return
                end
                
                -- Get current cursor position
                local bufnr = vim.api.nvim_get_current_buf()
                local cursor_pos = vim.api.nvim_win_get_cursor(0)
                local line = cursor_pos[1] - 1  -- Convert to 0-based indexing
                local col = cursor_pos[2]
                
                -- Check for diagnostics at current position
                local diagnostics = vim.diagnostic.get(bufnr, {
                    lnum = line,
                })
                
                -- Filter diagnostics that actually contain the cursor position
                local relevant_diagnostics = {}
                for _, diagnostic in ipairs(diagnostics) do
                    if diagnostic.lnum == line and 
                       col >= diagnostic.col and 
                       col <= diagnostic.end_col then
                        table.insert(relevant_diagnostics, diagnostic)
                    end
                end
                
                -- If we have diagnostics at cursor position, show them
                if #relevant_diagnostics > 0 then
                    vim.diagnostic.open_float({
                        bufnr = bufnr,
                        scope = "cursor",
                        border = "rounded",
                        source = "always",
                        header = "",
                        prefix = "",
                    })
                    return
                end
                
                -- No diagnostics at cursor, try to show documentation
                -- Get the first LSP client to determine position encoding
                local clients = vim.lsp.get_clients({ bufnr = bufnr })
                local position_encoding = 'utf-16'  -- Default fallback
                if clients and #clients > 0 then
                    position_encoding = clients[1].offset_encoding or 'utf-16'
                end
                
                local params = vim.lsp.util.make_position_params(0, position_encoding)
                vim.lsp.buf_request(0, 'textDocument/hover', params, function(err, result, ctx, config)
                    if err or not result or not result.contents then
                        vim.notify("No diagnostics or documentation available", vim.log.levels.INFO)
                        return
                    end
                    
                    local contents = result.contents
                    local lines = {}
                    
                    if type(contents) == "string" then
                        lines = vim.split(contents, '\n')
                    elseif contents.kind == "markdown" then
                        lines = vim.split(contents.value, '\n')
                    elseif type(contents) == "table" then
                        for _, item in ipairs(contents) do
                            if type(item) == "string" then
                                vim.list_extend(lines, vim.split(item, '\n'))
                            elseif item.value then
                                vim.list_extend(lines, vim.split(item.value, '\n'))
                            end
                        end
                    end
                    
                    if #lines == 0 then
                        vim.notify("No diagnostics or documentation available", vim.log.levels.INFO)
                        return
                    end
                    
                    -- Create popup window
                    local width = math.min(80, vim.o.columns - 10)
                    local height = math.min(20, #lines + 2)
                    
                    local buf = vim.api.nvim_create_buf(false, true)
                    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
                    vim.api.nvim_buf_set_option(buf, 'modifiable', false)
                    vim.api.nvim_buf_set_option(buf, 'filetype', 'markdown')
                    
                    local win_opts = {
                        relative = 'cursor',
                        width = width,
                        height = height,
                        row = 1,
                        col = 0,
                        border = 'rounded',
                        style = 'minimal',
                        title = ' Documentation ',
                        title_pos = 'center',
                    }
                    
                    local win = vim.api.nvim_open_win(buf, false, win_opts)
                    vim.api.nvim_win_set_option(win, 'winhl', 'Normal:Pmenu,FloatBorder:PmenuBorder')
                    
                    -- Store window reference for toggle behavior
                    vim.g.lsp_smart_popup_win = win
                    
                    -- Close popup on cursor move or escape
                    local close_events = {'CursorMoved', 'CursorMovedI', 'BufLeave', 'InsertEnter'}
                    local group = vim.api.nvim_create_augroup('LSPSmartPopup', {clear = false})
                    
                    vim.api.nvim_create_autocmd(close_events, {
                        group = group,
                        buffer = vim.api.nvim_get_current_buf(),
                        callback = function()
                            if vim.api.nvim_win_is_valid(win) then
                                vim.api.nvim_win_close(win, true)
                            end
                            vim.g.lsp_smart_popup_win = nil
                            vim.api.nvim_del_augroup_by_id(group)
                        end,
                        once = true,
                    })
                    
                    -- Also allow manual closing with 'q' or <Esc>
                    vim.keymap.set('n', 'q', function()
                        if vim.api.nvim_win_is_valid(win) then
                            vim.api.nvim_win_close(win, true)
                            vim.g.lsp_smart_popup_win = nil
                        end
                    end, {buffer = buf, nowait = true})
                    
                    vim.keymap.set('n', '<Esc>', function()
                        if vim.api.nvim_win_is_valid(win) then
                            vim.api.nvim_win_close(win, true)
                            vim.g.lsp_smart_popup_win = nil
                        end
                    end, {buffer = buf, nowait = true})
                end)
            end, opts)


        end

        local capabilities = cmp_nvim_lsp.default_capabilities()

        -- Configure diagnostic display
        vim.diagnostic.config({
            virtual_text = false,  -- Hide inline error text
            signs = true,          -- Keep error indicators in sign column
            underline = true,      -- Keep error underlines
            update_in_insert = false,
            severity_sort = true,
            float = {
                border = "rounded",
                source = "always",
                header = "",
                prefix = "",
            },
        })

        local signs = { Error = "E ", Warn = "W ", Hint = "H ", Info = "i " }
        for type, icon in pairs(signs) do
            local hl = "DiagnosticSign" .. type
            vim.fn.sign_define(hl, { text = icon, texthl = hl, numhl = "" })
        end

        lspconfig["jdtls"].setup({
            capabilities = capabilities,
            on_attach = on_attach,
        })

        lspconfig["clangd"].setup({
            capabilities = capabilities,
            on_attach = on_attach,
        })

        lspconfig["basedpyright"].setup({
            cmd = { "/home/mojolake/.nix-profile/bin/basedpyright-langserver", "--stdio" },
            capabilities = capabilities,
            on_attach = on_attach,
            settings = {
                basedpyright = {
                    typeCheckingMode = "standard",
                },
            },
        })

        lspconfig["rust_analyzer"].setup({
            capabilities = capabilities,
            on_attach = on_attach,
            settings = {
                ["rust-analyzer"] = {
                    inlayHints = {
                        chainingHints = {
                            enable = true,
                        },
                        parameterHints = {
                            enable = true,
                        },
                        typeHints = {
                            enable = true,
                        },
                    },
                },
            },
        })

        -- lspconfig["lua_ls"].setup({
        --     capabilities = capabilities,
        --     on_attach = on_attach,
        --
        --     settings = {
        --         Lua = {
        --             diagnostics = {
        --                 globals = { "vim" },
        --             },
        --             workspace = {
        --                 library = {
        --                     [vim.fn.expand("$VIMRUNTIME/lua")] = true,
        --                     [vim.fn.stdpath("config") .. "/lua"] = true,
        --                 }
        --             }
        --         }
        --     }
        -- })

        lspconfig["ts_ls"].setup({
            capabilities = capabilities,
            on_attach = on_attach,
            settings = {
                jsx = "react",
                tsx = "react",
            },
        })

        lspconfig["zls"].setup({
            capabilities = capabilities,
            on_attach = on_attach,
        })

        -- Modern inlay hints setup using LspAttach autocmd
        vim.api.nvim_create_autocmd("LspAttach", {
            group = vim.api.nvim_create_augroup("UserLspConfig", {}),
            callback = function(args)
                local client = vim.lsp.get_client_by_id(args.data.client_id)
                if client and client.server_capabilities.inlayHintProvider then
                    -- Enable inlay hints for this buffer
                    vim.lsp.inlay_hint.enable(true, { bufnr = args.buf })
                    
                    -- Add keymap to toggle inlay hints (using 'th' for toggle hints)
                    vim.keymap.set("n", "<leader>th", function()
                        local current_setting = vim.lsp.inlay_hint.is_enabled({ bufnr = args.buf })
                        vim.lsp.inlay_hint.enable(not current_setting, { bufnr = args.buf })
                    end, { buffer = args.buf, desc = "Toggle inlay hints" })
                end
            end,
        })

    end,
}
