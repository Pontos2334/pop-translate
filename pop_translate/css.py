"""Visual tokens and GTK4 component styles.

Design intent: the translation/explanation is the hero. Chrome (header, tabs,
source preview, settings) stays compact while keeping every label readable.
The result gets the largest share of the popup's height. Every color/size is a
token: change it here, not in per-widget code.
"""

CSS = b"""
@define-color ink #2b2435;
@define-color ink_soft #4c4459;
@define-color muted #6f687d;
@define-color faint #918a9e;
@define-color line #e9e4ef;
@define-color line_soft #f2eef6;
@define-color canvas #f7f4fa;
@define-color canvas_soft #fbf9fd;
@define-color surface #fefdff;
@define-color accent #6e4b95;
@define-color accent_hover #5c3d80;
@define-color accent_soft #f2ebfa;
@define-color accent_line #e3d8f0;
@define-color danger #b4425a;
@define-color danger_soft #fcf0f3;
@define-color success #3c8068;
@define-color success_soft #edf7f2;

/* ---- surfaces ---- */

.translate-window, .setup-window {
    /* Keep the desktop font family, with explicit readable sizes and medium
       body weight. Controls use semibold to remain clear at smaller sizes. */
    font-size: 15px;
    font-weight: 500;
    color: @ink;
    background-color: @surface;
    border: 1px solid @line;
    border-radius: 16px;
}
.translate-window { box-shadow: 0 12px 40px rgba(52, 33, 68, 0.16); }

/* ---- header: one compact row ---- */

.app-header {
    padding: 7px 10px;
    background-color: @canvas_soft;
    border-bottom: 1px solid @line_soft;
    border-radius: 16px 16px 0 0;
}
.app-mark {
    background-color: @accent_soft;
    color: @accent;
    border-radius: 7px;
    padding: 5px;
    margin-right: 7px;
}
.tab-btn {
    min-height: 16px;
    min-width: 16px;
    font-size: 14px;
    font-weight: 600;
    padding: 5px 9px;
    border: none;
    border-radius: 7px;
    color: @muted;
    background: transparent;
    box-shadow: none;
}
.tab-btn:hover { background-color: @canvas; color: @ink_soft; }
.tab-btn.active {
    color: @accent;
    background-color: @accent_soft;
    font-weight: 600;
}
.icon-btn, .close-btn {
    min-width: 16px;
    min-height: 16px;
    padding: 5px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: @muted;
    box-shadow: none;
}
.icon-btn:hover { background-color: @canvas; color: @ink; }
.close-btn:hover { background-color: @danger_soft; color: @danger; }
.icon-btn.pin-active { background-color: @accent_soft; color: @accent; }
.mini-btn {
    min-width: 14px;
    min-height: 14px;
    padding: 3px;
    border: none;
    border-radius: 5px;
    background: transparent;
    color: @faint;
    box-shadow: none;
}
.mini-btn:hover { background-color: @canvas; color: @ink_soft; }
.mini-btn.copied { color: @success; }

/* ---- content: source first, result hero ---- */

.content-area { background-color: @surface; }
.content-box { padding: 12px 18px 16px; }
.section-label {
    color: @muted;
    font-size: 13px;
    font-weight: 600;
}
.source-text, .source-text text {
    color: @ink_soft;
    font-size: 15px;
    font-weight: 500;
    line-height: 1.5;
    background: transparent;
    border: none;
    padding: 0;
}
.source-text selection { background-color: @accent_soft; color: @ink; }
.content-divider {
    background-color: @line_soft;
    min-height: 1px;
    margin: 12px 0;
}
.result {
    color: @ink;
    font-size: 18px;
    font-weight: 500;
    line-height: 1.6;
    background: transparent;
    border: none;
    padding: 0;
}
.result text {
    color: @ink;
    font-size: 18px;
    font-weight: 500;
    background: transparent;
}
.result-explain, .result-explain text { font-size: 17px; font-weight: 500; }

.stream-status { color: @muted; font-size: 13px; }
.stream-spinner { color: @accent; }

.hint { color: @muted; font-size: 13px; padding: 2px 0; }
.error-hint { color: @danger; font-size: 13px; padding: 2px 0; }
.error-banner {
    background-color: @danger_soft;
    border: 1px solid #f0d2dc;
    border-radius: 8px;
    padding: 6px 10px;
}
.error-banner label { color: @danger; font-size: 13px; }

.text-btn {
    min-height: 16px;
    padding: 3px 7px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: @muted;
    font-size: 14px;
    font-weight: 600;
    box-shadow: none;
}
.text-btn:hover { background-color: @canvas; color: @ink; }
.text-btn.primary { color: @accent; background-color: @accent_soft; }
.text-btn.primary:hover { background-color: @accent_line; }
.text-btn.copy { color: @accent; background-color: @accent_soft; }
.text-btn.copy:hover { background-color: @accent_line; }
.text-btn.copied { color: @success; background-color: @success_soft; }

.action-btn {
    min-height: 18px;
    padding: 6px 11px;
    font-size: 14px;
    font-weight: 600;
    border: 1px solid @line;
    border-radius: 7px;
    background-color: @surface;
    color: @ink_soft;
    box-shadow: none;
}
.action-btn:hover { background-color: @canvas; border-color: #d9d0e3; color: @ink; }
.action-btn.primary {
    background-color: @accent;
    border-color: @accent;
    color: #ffffff;
    font-weight: 600;
}
.action-btn.primary:hover { background-color: @accent_hover; border-color: @accent_hover; }
.action-btn.primary label { color: #ffffff; }
.action-btn.primary:disabled { background-color: #cdbddf; border-color: #cdbddf; }
.action-btn.primary:disabled label { color: #ffffff; }
.action-btn:disabled { color: #a29aab; background-color: @canvas; border-color: @line; }
.action-btn:disabled label { color: #a29aab; }

/* ---- footer: secondary settings, never the focus ---- */

.status-bar {
    padding: 5px 12px;
    background-color: @canvas_soft;
    border-top: 1px solid @line_soft;
    border-radius: 0 0 16px 16px;
}
.speed-label { color: @muted; font-size: 13px; }

dropdown.model-select { background: transparent; border: none; padding: 0; }
dropdown.model-select > button {
    min-height: 18px;
    padding: 4px 9px;
    border: 1px solid @accent_line;
    border-radius: 8px;
    background: @accent_soft;
    color: @accent;
    font-size: 14px;
    font-weight: 600;
    box-shadow: none;
}
dropdown.model-select > button:hover,
dropdown.model-select > button:checked {
    background: @accent_line;
    border-color: #d4c3e6;
}
/* GTK also renders the button's current item as a row. Keep the desktop
   theme's blue hover/selection background out of this inner row. */
dropdown.model-select > button row,
dropdown.model-select > button row:hover,
dropdown.model-select > button row:selected {
    background: transparent;
    color: @accent;
    box-shadow: none;
}
dropdown.model-select arrow { color: @accent; opacity: 0.65; margin-left: 5px; }
dropdown.model-select popover > contents {
    padding: 5px;
    border-radius: 12px;
}
dropdown.model-select popover listview {
    min-width: 216px;
    padding: 0;
    background: transparent;
    color: @ink_soft;
}
dropdown.model-select popover listview > row {
    padding: 0;
    margin: 2px;
    border: none;
    border-radius: 8px;
    background: transparent;
    box-shadow: none;
    outline-offset: -2px;
}
dropdown.model-select popover listview > row:hover,
dropdown.model-select popover listview > row:selected {
    background: @canvas;
    color: @ink;
}
.model-option { padding: 8px 10px; border-radius: 8px; }
dropdown.model-select popover row:selected .model-option { background: @accent_soft; }
.model-option-name { font-size: 14px; font-weight: 600; color: @ink_soft; }
dropdown.model-select popover row:selected .model-option-name { color: @accent; font-weight: 600; }
.model-option-id { font-size: 13px; font-weight: 500; color: @muted; }
.model-option-check { color: @accent; }

checkbutton.thinking-toggle {
    font-size: 14px;
    font-weight: 600;
    color: @muted;
    padding: 2px 4px;
    border-radius: 6px;
}
checkbutton.thinking-toggle:hover { color: @ink_soft; background-color: @canvas; }
checkbutton.thinking-toggle:checked { color: @accent; }
.thinking-toggle check {
    min-width: 12px;
    min-height: 12px;
    border: 1.5px solid #cfc6da;
    border-radius: 3px;
    background-color: @surface;
    box-shadow: none;
}
.thinking-toggle check:checked { border-color: @accent; background-color: @accent; color: #ffffff; }

.mode-group { background-color: @canvas; border-radius: 7px; padding: 2px; }
.mode-btn {
    min-height: 16px;
    padding: 3px 9px;
    border: none;
    border-radius: 5px;
    background: transparent;
    color: @muted;
    font-size: 14px;
    font-weight: 600;
    box-shadow: none;
}
.mode-btn:hover { color: @ink; }
.mode-btn.active {
    background-color: @surface;
    color: @accent;
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(43, 36, 53, 0.08);
}

.chip-toggle {
    min-height: 16px;
    padding: 3px 8px;
    border: 1px solid transparent;
    border-radius: 6px;
    background-color: transparent;
    color: @muted;
    font-size: 14px;
    font-weight: 600;
    box-shadow: none;
}
.chip-toggle:hover { background-color: @canvas; color: @ink; }
.chip-toggle.context-active { background-color: @accent_soft; color: @accent; }

/* ---- editing ---- */

.source-edit {
    background-color: @canvas_soft;
    border: 1px solid @line;
    border-radius: 8px;
    padding: 7px 10px;
}
.source-edit:focus-within {
    background-color: @surface;
    border-color: #c8b6e0;
    box-shadow: 0 0 0 2px rgba(110, 75, 149, 0.10);
}
.source-edit text { background: transparent; color: @ink; font-size: 16px; font-weight: 500; }

/* ---- chat ---- */

.chat-transcript { padding: 12px 16px 14px; }
.chat-row, .chat-bubble-wrap { background: transparent; }
.chat-bubble-user {
    background-color: @accent_soft;
    border-radius: 10px;
    padding: 6px 10px;
}
.chat-bubble-ai { background: transparent; padding: 0; }
.message-text, .message-text text {
    color: @ink;
    font-size: 16px;
    font-weight: 500;
    line-height: 1.6;
    background: transparent;
    border: none;
    padding: 0;
}
.chat-bubble-user .message-text, .chat-bubble-user .message-text text {
    color: #3f334d;
    font-size: 16px;
}
.chat-bubble-actions { margin-top: 2px; }
.chat-bubble-action-btn {
    min-height: 12px;
    padding: 1px 5px;
    font-size: 13px;
    font-weight: 600;
    border: none;
    border-radius: 4px;
    color: @muted;
    background: transparent;
    box-shadow: none;
}
.chat-bubble-user .chat-bubble-action-btn { color: @muted; }
.chat-bubble-action-btn:hover { color: @accent; background-color: @accent_soft; }
.chat-bubble-action-btn:disabled { color: #c3bccd; }
.chat-bubble-edit-view, .chat-bubble-edit-view text {
    font-size: 16px;
    font-weight: 500;
    line-height: 1.5;
    background: transparent;
    color: @ink;
    border: none;
    padding: 0;
}
.chat-bubble-edit-sw { background: transparent; border: none; }

.chat-thinking-expander { margin-bottom: 2px; font-size: 13px; font-weight: 600; color: @muted; }
.chat-bubble-thinking-text, .chat-bubble-thinking-text text {
    font-size: 14px;
    font-weight: 500;
    line-height: 1.55;
    color: @muted;
    background: transparent;
    border: none;
    padding: 0;
}
.chat-bubble-thinking-text {
    border-left: 2px solid @line;
    padding-left: 8px;
    margin: 3px 0 6px;
}

.chat-composer {
    padding: 7px 14px 10px;
    border-top: 1px solid @line_soft;
    background-color: @surface;
    border-radius: 0 0 16px 16px;
}
.composer-card {
    background-color: @canvas_soft;
    border: 1px solid @line;
    border-radius: 10px;
    padding: 3px 6px 4px 9px;
}
.composer-card:focus-within {
    background-color: @surface;
    border-color: #c8b6e0;
    box-shadow: 0 0 0 2px rgba(110, 75, 149, 0.10);
}
.composer-card scrolledwindow { border: none; background: transparent; }
.chat-input-view { font-size: 16px; font-weight: 500; background: transparent; color: @ink; padding: 7px 0; }
.chat-input-view text { background: transparent; color: @ink; font-weight: 500; }
.chat-input-placeholder { font-size: 16px; color: @muted; }
.chat-send {
    min-height: 16px;
    padding: 4px 12px;
    font-size: 14px;
    font-weight: 600;
    border: 1px solid @accent;
    border-radius: 6px;
    background-color: @accent;
    color: #ffffff;
    box-shadow: none;
}
.chat-send:hover { background-color: @accent_hover; border-color: @accent_hover; }
.chat-send label { color: #ffffff; }
.chat-send:disabled { background-color: #f0ecf5; border-color: #f0ecf5; color: #a29aab; }
.chat-send:disabled label { color: #a29aab; }
.chat-send.stop { background-color: @danger_soft; border-color: #efd2dc; color: @danger; }
.chat-send.stop label { color: @danger; }

/* ---- vision ---- */

.vision-attachment {
    padding: 6px 12px;
    background-color: @canvas_soft;
    border-bottom: 1px solid @line_soft;
}
menubutton.vision-thumb > button {
    padding: 0;
    border: 1px solid @line;
    border-radius: 6px;
    background-color: @surface;
    box-shadow: none;
    min-width: 44px;
    min-height: 32px;
}
menubutton.vision-thumb > button:hover { border-color: #d8cde5; }
.vision-image { border-radius: 5px; }
.attachment-title { font-size: 14px; font-weight: 600; color: @ink; }
.attachment-hint { font-size: 13px; color: @muted; }

/* ---- empty states ---- */

.empty-state { padding: 20px 18px; }
.empty-state-icon {
    color: @accent;
    background-color: @accent_soft;
    padding: 8px;
    border-radius: 10px;
}
.empty-state-title { font-size: 18px; font-weight: 600; color: @ink; }
.empty-state-hint { font-size: 14px; color: @muted; }

/* ---- overlays ---- */

popover.background > contents {
    border-radius: 10px;
    padding: 10px 12px;
    border: 1px solid @line;
    background-color: @surface;
    box-shadow: 0 10px 28px rgba(52, 33, 68, 0.16);
}
.help-title { font-size: 15px; font-weight: 600; color: @ink; }
.help-row { font-size: 14px; color: @ink_soft; }
.help-desc { font-size: 14px; color: @muted; }
.kbd {
    font-family: "monospace";
    font-size: 13px;
    color: @ink_soft;
    background-color: @canvas;
    border: 1px solid @line;
    border-radius: 4px;
    padding: 0 5px;
}

/* ---- setup wizard ---- */

.setup-content { padding: 20px 24px 16px; }
.setup-header { margin-bottom: 2px; }
.setup-title { font-size: 20px; font-weight: 700; color: @ink; }
.setup-description { color: @muted; font-size: 14px; margin-bottom: 2px; }
.setup-field { margin-top: 3px; }
.setup-label { font-size: 14px; font-weight: 600; color: @muted; }
.setup-entry {
    font-size: 16px;
    font-weight: 500;
    padding: 7px 10px;
    border: 1px solid @line;
    border-radius: 7px;
    background-color: @surface;
    color: @ink;
    box-shadow: none;
}
.setup-entry:focus {
    border-color: #c8b6e0;
    box-shadow: 0 0 0 2px rgba(110, 75, 149, 0.10);
}
.setup-footer {
    padding: 11px 24px;
    border-top: 1px solid @line_soft;
    background-color: @canvas_soft;
    border-radius: 0 0 16px 16px;
}
.setup-cancel {
    min-height: 18px;
    padding: 6px 12px;
    font-size: 14px;
    font-weight: 600;
    border: 1px solid @line;
    border-radius: 7px;
    background-color: @surface;
    color: @ink_soft;
    box-shadow: none;
}
.setup-cancel:hover { background-color: @canvas; color: @ink; }
.setup-save {
    min-height: 18px;
    padding: 6px 14px;
    font-size: 14px;
    font-weight: 600;
    border: 1px solid @accent;
    border-radius: 7px;
    background-color: @accent;
    color: #ffffff;
    box-shadow: none;
}
.setup-save:hover { background-color: @accent_hover; border-color: @accent_hover; }
.setup-save label { color: #ffffff; }

/* ---- focus & scrollbars ---- */

button:focus-visible, dropdown:focus-visible, checkbutton:focus-visible {
    outline: 2px solid #c8b6e0;
    outline-offset: 1px;
}
scrollbar slider { background-color: #ddd5e4; border-radius: 999px; }
scrollbar slider:hover { background-color: #c9bed6; }
"""
