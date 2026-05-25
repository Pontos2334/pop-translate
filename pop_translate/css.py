CSS = b"""
/* Global Reset and Base Styles */
* {
    font-family: "Inter", "Cantarell", "system-ui", "-apple-system", "BlinkMacSystemFont", "Roboto", "Noto Sans CJK SC", "Source Han Sans CN", "Microsoft YaHei", sans-serif;
    outline: none;
}

/* Window Frame & Shadow (macOS Native Utility Panel Look) */
.translate-window {
    background-color: #ffffff;
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    color: #18181b;
}

/* Setup Window Styling */
.setup-window {
    background-color: #ffffff;
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    color: #18181b;
}

/* Seamless Integrated Title Bar */
.title-bar {
    background-color: #f4f4f5;
    padding: 10px 14px;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    border-bottom: 1px solid #e4e4e7;
}

.title-label {
    color: #18181b;
    font-weight: 700;
    font-size: 13.5px;
    letter-spacing: -0.2px;
}

/* Minimalist Title Action Buttons */
.title-btn {
    color: #27272a;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: -0.1px;
    padding: 5px 12px;
    border: 1px solid #d4d4d8;
    border-radius: 6px;
    background-color: #ffffff;
    margin-right: 6px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    transition: all 0.15s ease-in-out;
}

.title-btn:hover {
    background-color: #f4f4f5;
    color: #09090b;
    border-color: #a1a1aa;
}

.close-btn {
    color: #71717a;
    font-size: 13px;
    font-weight: 600;
    padding: 5px 10px;
    border: none;
    border-radius: 6px;
    background-color: transparent;
    transition: all 0.15s ease-in-out;
}

.close-btn:hover {
    background-color: #ef4444;
    color: #ffffff;
}

/* Pill-Style Segmented Tab Bar (macOS System Style) */
.tab-bar {
    padding: 6px 12px;
    background-color: #f4f4f5;
    border-bottom: 1px solid #e4e4e7;
}

.tab-btn {
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: -0.1px;
    padding: 6px 16px;
    border: none;
    border-radius: 6px;
    background-color: transparent;
    color: #71717a;
    margin-right: 4px;
    transition: all 0.15s ease;
}

.tab-btn:hover {
    color: #18181b;
    background-color: rgba(0, 0, 0, 0.04);
}

.tab-btn.active {
    color: #18181b;
    background-color: #ffffff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 1px rgba(0, 0, 0, 0.05);
    font-weight: 700;
}

/* Main Content Box */
.content-box {
    padding: 16px;
}

/* Original Source Card Layout (Minimalist card) */
.orig-card {
    background-color: #f4f4f5;
    border-left: 3px solid #71717a;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 14px;
    border-top: 1px solid #e4e4e7;
    border-right: 1px solid #e4e4e7;
    border-bottom: 1px solid #e4e4e7;
}

.orig {
    color: #18181b;
    font-size: 13.5px;
    line-height: 1.5;
    letter-spacing: -0.1px;
}

.orig-edit {
    color: #18181b;
    font-size: 13.5px;
    padding: 8px;
    border: 1px solid #71717a;
    border-radius: 6px;
    background-color: #ffffff;
    line-height: 1.5;
}

.sep {
    min-height: 1px;
    background-color: #e4e4e7;
    margin: 12px 0;
}

/* Translation & Explanation Unified Typography */
.result {
    color: #18181b;
    font-size: 14px;
    font-weight: 500;
    line-height: 1.6;
    padding: 2px 0;
    letter-spacing: -0.1px;
}

.explain-title {
    color: #18181b;
    font-size: 13.5px;
    font-weight: 700;
    margin-top: 8px;
    margin-bottom: 4px;
    letter-spacing: -0.1px;
}

.explain-body {
    color: #18181b;
    font-size: 14px;
    font-weight: 500;
    line-height: 1.6;
    letter-spacing: -0.1px;
}

.hint {
    color: #71717a;
    font-size: 13px;
    font-style: italic;
    padding: 6px 0;
}

/* Control and Action Bars */
.button-bar {
    margin-top: 14px;
}

.control-bar {
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid #e4e4e7;
}

.chat-control-bar {
    padding: 6px 12px;
    background-color: #f4f4f5;
    border-bottom: 1px solid #e4e4e7;
}

/* Exquisite DropDown Select Redesign */
dropdown.model-select {
    min-width: 140px;
    background: transparent;
    border: none;
    padding: 0;
}

dropdown.model-select button {
    background-color: #ffffff;
    border: 1px solid #d4d4d8;
    border-radius: 6px;
    padding: 5px 12px;
    color: #27272a;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: -0.1px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

dropdown.model-select button:hover {
    background-color: #f4f4f5;
    color: #09090b;
    border-color: #a1a1aa;
}

dropdown.model-select button arrow {
    color: #71717a;
    margin-left: 6px;
}

.thinking-toggle {
    font-size: 12px;
    color: #71717a;
    margin-left: 6px;
}

.thinking-toggle:hover {
    color: #18181b;
}

/* Ultra-Premium Button Redesigns */
.action-btn {
    font-size: 12.5px;
    font-weight: 600;
    letter-spacing: -0.1px;
    padding: 6px 16px;
    border: 1px solid #d4d4d8;
    border-radius: 6px;
    background-color: #ffffff;
    color: #27272a;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.action-btn:hover {
    background-color: #f4f4f5;
    color: #09090b;
    border-color: #a1a1aa;
}

.action-btn:disabled {
    color: #a1a1aa;
    background-color: #f4f4f5;
    border-color: #e4e4e7;
    box-shadow: none;
}

/* Matte Graphite/Black for Primary Buttons - Peak Sophociation */
.action-btn.primary {
    color: #ffffff;
    background-color: #18181b;
    border: 1px solid #18181b;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.action-btn.primary:hover {
    background-color: #27272a;
    border-color: #27272a;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.12);
}

/* Elegant Ocean Accent for Copy Button */
.action-btn.copy {
    color: #0969da;
    border-color: rgba(9, 105, 218, 0.15);
    background-color: rgba(9, 105, 218, 0.05);
}

.action-btn.copy:hover {
    color: #ffffff;
    background-color: #0969da;
    border-color: #0969da;
}

/* Custom Styled Scrollbar (Thin macOS Style) */
scrollbar {
    background-color: transparent;
}

scrollbar slider {
    background-color: rgba(0, 0, 0, 0.08);
    border-radius: 4px;
    min-width: 3px;
    min-height: 3px;
    transition: background-color 0.15s;
}

scrollbar slider:hover {
    background-color: rgba(0, 0, 0, 0.18);
}

/* Shortcut Instruction Bar */
.shortcut-bar {
    padding: 6px 14px;
    background-color: #f4f4f5;
    border-top: 1px solid #e4e4e7;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}

.shortcut-hint {
    color: #71717a;
    font-size: 11.5px;
    letter-spacing: -0.1px;
}

/* Premium Chat Layout */
.chat-area {
    padding: 14px;
}

.chat-bubble-user {
    background-color: #18181b;
    color: #ffffff;
    border-radius: 12px 12px 2px 12px;
    padding: 10px 14px;
    font-size: 13px;
    line-height: 1.5;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.chat-bubble-ai {
    background-color: #f4f4f5;
    color: #18181b;
    border-radius: 12px 12px 12px 2px;
    padding: 10px 14px;
    font-size: 13px;
    line-height: 1.5;
    border: 1px solid #e4e4e7;
}

.chat-input-bar {
    padding: 10px 14px;
    border-top: 1px solid #e4e4e7;
    background-color: #f4f4f5;
}

.chat-input-bar scrolledwindow {
    border: 1px solid #d4d4d8;
    border-radius: 6px;
    background-color: #ffffff;
    transition: all 0.15s ease;
}

.chat-input-bar scrolledwindow:focus-within {
    border-color: #18181b;
    box-shadow: 0 0 0 2px rgba(24, 24, 27, 0.1);
}

.chat-input-view {
    font-size: 13px;
    padding: 6px 8px;
    background-color: #ffffff;
    color: #18181b;
    border: none;
}




.chat-send {
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: -0.1px;
    padding: 6px 16px;
    border: 1px solid #18181b;
    border-radius: 6px;
    background-color: #18181b;
    color: #ffffff;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
    transition: all 0.15s ease;
}

.chat-send:hover {
    background-color: #27272a;
    border-color: #27272a;
}

.chat-send:disabled {
    background-color: #f4f4f5;
    color: #d4d4d8;
    border-color: #e4e4e7;
    box-shadow: none;
}

/* Setup Dialog Specific Polish */
.setup-title {
    color: #18181b;
    font-weight: 800;
    font-size: 18px;
    letter-spacing: -0.2px;
}

.setup-label {
    color: #71717a;
    font-size: 12.5px;
    font-weight: 600;
    margin-bottom: 2px;
}

.setup-entry {
    font-size: 13px;
    padding: 8px 10px;
    border: 1px solid #d4d4d8;
    border-radius: 6px;
    background-color: #ffffff;
    color: #18181b;
    transition: all 0.15s ease;
}

.setup-entry:focus {
    border-color: #18181b;
    box-shadow: 0 0 0 2px rgba(24, 24, 27, 0.1);
}

.setup-save {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: -0.1px;
    padding: 8px 22px;
    border: 1px solid #18181b;
    border-radius: 6px;
    background-color: #18181b;
    color: #ffffff;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
    transition: all 0.15s ease;
}

.setup-save:hover {
    background-color: #27272a;
    border-color: #27272a;
}

.setup-cancel {
    font-size: 13px;
    font-weight: 600;
    padding: 8px 22px;
    border: 1px solid #d4d4d8;
    border-radius: 6px;
    background-color: #ffffff;
    color: #27272a;
    transition: all 0.15s ease;
}

.setup-cancel:hover {
    background-color: #f4f4f5;
    border-color: #a1a1aa;
}

.error-hint {
    color: #ef4444;
    font-size: 12px;
    margin-top: 4px;
}
"""
