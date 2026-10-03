from flask import Flask, jsonify, request, render_template_string, Response
from flask_cors import CORS
import os
import subprocess
import voice_dictation
from voice_dictation import VoiceDictationApp

app = Flask(__name__)
_ui_port = int(os.getenv("VOICE_TYPING_UI_PORT", "3221"))
_ui_host = os.getenv("VOICE_TYPING_UI_HOST", "127.0.0.1")
_cors_origins = [f"http://127.0.0.1:{_ui_port}", f"http://localhost:{_ui_port}"]
if _ui_host not in ("127.0.0.1", "localhost"):
    _cors_origins.append(f"http://{_ui_host}:{_ui_port}")
CORS(app, origins=_cors_origins)

# Initialize the dictation app
dict_app = VoiceDictationApp()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Typing Console</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19;
            --card: #161c2e;
            --primary: #38bdf8;
            --accent: #818cf8;
            --text: #f1f5f9;
            --text-dim: #94a3b8;
            --success: #4ade80;
            --danger: #fb7185;
            --border: rgba(255, 255, 255, 0.08);
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background-image: radial-gradient(circle at 50% 50%, #1e293b 0%, #0b0f19 100%);
        }

        .container {
            width: 100%;
            max-width: 700px;
            padding: 2rem;
        }

        .card {
            background-color: var(--card);
            border-radius: 32px;
            padding: 3rem;
            box-shadow: 0 50px 100px -20px rgba(0, 0, 0, 0.7);
            border: 1px solid var(--border);
            backdrop-filter: blur(20px);
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 2.5rem;
        }

        h1 {
            margin: 0 0 0.25rem 0;
            font-weight: 600;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.8rem;
            letter-spacing: -0.02em;
        }

        .subtitle {
            color: var(--text-dim);
            font-size: 1.1rem;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.6rem 1.2rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .status-on { background: rgba(74, 222, 128, 0.1); color: var(--success); box-shadow: 0 0 20px rgba(74, 222, 128, 0.15); }
        .status-off { background: rgba(251, 113, 133, 0.1); color: var(--danger); }

        .form-section {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2.5rem;
            padding: 2rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 20px;
            border: 1px solid var(--border);
        }

        .input-group {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .input-group label {
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        input, select {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            padding: 0.75rem 1rem;
            border-radius: 12px;
            color: var(--text);
            font-family: inherit;
            font-size: 0.95rem;
            transition: all 0.2s;
        }

        input:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
        }

        .full-width { grid-column: span 2; }

        .controls {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 1rem;
            margin-bottom: 2.5rem;
        }

        button {
            padding: 1.1rem 1.5rem;
            border-radius: 16px;
            border: none;
            cursor: pointer;
            font-weight: 600;
            font-family: inherit;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 1.05rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: white;
            box-shadow: 0 10px 25px -5px rgba(56, 189, 248, 0.4);
        }

        .btn-primary:hover {
            transform: translateY(-3px);
            filter: brightness(1.1);
            box-shadow: 0 20px 30px -10px rgba(56, 189, 248, 0.6);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.08);
            transform: translateY(-2px);
        }

        .log-container {
            background: #080c14;
            border-radius: 20px;
            padding: 1.5rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            height: 120px;
            overflow-y: auto;
            border: 1px solid var(--border);
            margin-top: 2rem;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);
        }

        .log-entry { 
            margin-bottom: 0.75rem; 
            padding-left: 1rem;
            color: var(--primary);
            opacity: 0;
            transform: translateX(-10px);
            animation: fadeIn 0.4s forwards;
        }

        @keyframes fadeIn {
            to { opacity: 1; transform: translateX(0); }
        }

        .recording-indicator {
            width: 10px;
            height: 10px;
            background: var(--danger);
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 15px var(--danger);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.2); }
            100% { opacity: 1; transform: scale(1); }
        }

        .save-banner {
            position: fixed;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%);
            background: var(--success);
            color: #000;
            padding: 0.75rem 2rem;
            border-radius: 99px;
            font-weight: 600;
            box-shadow: 0 10px 30px rgba(74, 222, 128, 0.4);
            display: none;
            z-index: 100;
        }

        .mic-meter {
            display: none;
            margin-top: 1.5rem;
            padding: 1.25rem 1.5rem;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 16px;
            border: 1px solid var(--border);
        }

        .mic-meter.visible {
            display: block;
        }

        .meter-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }

        .meter-label {
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .meter-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .meter-db {
            font-size: 1.1rem;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
            min-width: 4.5rem;
            text-align: right;
        }

        .meter-db.low { color: var(--success); }
        .meter-db.mid { color: var(--primary); }
        .meter-db.high { color: var(--danger); }

        .meter-timer {
            color: var(--text-dim);
            font-size: 0.85rem;
            font-variant-numeric: tabular-nums;
        }

        .meter-track {
            display: flex;
            gap: 4px;
            height: 32px;
            align-items: flex-end;
        }

        .meter-bar {
            flex: 1;
            height: 4px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 3px;
            transition: height 0.06s ease, background 0.06s ease, box-shadow 0.06s ease;
            align-self: flex-end;
        }

        .meter-bar.lit {
            box-shadow: 0 0 6px rgba(56, 189, 248, 0.3);
        }

        .meter-bar:nth-child(1).lit,
        .meter-bar:nth-child(2).lit,
        .meter-bar:nth-child(3).lit { background: #4ade80; }
        .meter-bar:nth-child(4).lit,
        .meter-bar:nth-child(5).lit,
        .meter-bar:nth-child(6).lit { background: #38bdf8; }
        .meter-bar:nth-child(7).lit,
        .meter-bar:nth-child(8).lit,
        .meter-bar:nth-child(9).lit { background: #818cf8; }
        .meter-bar:nth-child(10).lit,
        .meter-bar:nth-child(11).lit,
        .meter-bar:nth-child(12).lit { background: #fb7185; }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            padding: 0.75rem 1rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 12px;
            border: 1px solid var(--border);
            margin-top: 1.5rem;
            user-select: none;
            transition: background 0.2s;
        }

        .section-header:hover {
            background: rgba(0, 0, 0, 0.35);
        }

        .section-header .label {
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .section-header .count {
            font-size: 0.75rem;
            color: var(--primary);
            font-weight: 600;
        }

        .section-header .chevron {
            color: var(--text-dim);
            font-size: 0.85rem;
            transition: transform 0.2s;
        }

        .section-header .chevron.open {
            transform: rotate(90deg);
        }

        .section-body {
            display: none;
            max-height: 200px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.15);
            border-radius: 12px;
            border: 1px solid var(--border);
            margin-top: 0.5rem;
            padding: 0.5rem 0;
        }

        .section-body.open {
            display: block;
        }

        .history-entry {
            display: flex;
            align-items: flex-start;
            gap: 0.6rem;
            padding: 0.5rem 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 0.85rem;
            cursor: pointer;
            transition: background 0.15s;
        }

        .history-entry:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        .history-entry:last-child {
            border-bottom: none;
        }

        .history-time {
            color: var(--text-dim);
            font-size: 0.75rem;
            white-space: nowrap;
            min-width: 3.5rem;
            padding-top: 0.05rem;
        }

        .history-text {
            color: var(--text);
            line-height: 1.4;
            word-break: break-word;
        }

        .history-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            flex-shrink: 0;
            margin-top: 0.35rem;
        }

        .history-dot.streaming { background: var(--primary); }
        .history-dot.batch { background: var(--accent); }
        .history-dot.command { background: #f59e0b; }

        .copy-btn {
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-dim);
            padding: 0.1rem 0.3rem;
            border-radius: 4px;
            font-size: 0.8rem;
            opacity: 0;
            transition: opacity 0.15s, color 0.2s, transform 0.15s;
            flex-shrink: 0;
            margin-left: auto;
            align-self: center;
            line-height: 1;
        }

        .history-entry:hover .copy-btn {
            opacity: 0.6;
        }

        .copy-btn.visible {
            opacity: 0.6;
        }

        .copy-btn:hover {
            opacity: 1 !important;
            color: var(--primary);
            transform: scale(1.1);
        }

        .copy-btn.copied {
            color: var(--success) !important;
            opacity: 1 !important;
        }

        .stt-test-area {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 1rem;
            margin-top: 1rem;
        }

        .stt-result {
            display: none;
            grid-column: span 2;
            padding: 1rem 1.25rem;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 14px;
            border: 1px solid var(--border);
            font-size: 0.85rem;
        }

        .stt-result.visible {
            display: block;
        }

        .stt-result .row {
            display: flex;
            justify-content: space-between;
            padding: 0.3rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }

        .stt-result .row:last-child {
            border-bottom: none;
        }

        .stt-result .key {
            color: var(--text-dim);
        }

        .stt-result .val {
            color: var(--text);
            text-align: right;
            max-width: 60%;
            word-break: break-word;
        }

        .stt-result .val.success { color: var(--success); }
        .stt-result .val.fail { color: var(--danger); }

        .btn-stt {
            background: linear-gradient(135deg, #a78bfa, #818cf8);
            color: white;
            box-shadow: 0 10px 25px -5px rgba(129, 140, 248, 0.4);
        }

        .btn-stt:hover {
            transform: translateY(-3px);
            filter: brightness(1.1);
            box-shadow: 0 20px 30px -10px rgba(129, 140, 248, 0.6);
        }

        .btn-stt:disabled {
            opacity: 0.5;
            transform: none;
            cursor: not-allowed;
        }

        .chip-input {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
            min-height: 60px;
            transition: border-color 0.2s, background 0.2s;
        }

        .chip-input:focus-within {
            border-color: var(--primary);
            background: rgba(255, 255, 255, 0.08);
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
        }

        .chip-list {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
        }

        .chip {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            background: rgba(129, 140, 248, 0.15);
            border: 1px solid rgba(129, 140, 248, 0.3);
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            color: var(--text);
            animation: chipIn 0.15s ease-out;
        }

        @keyframes chipIn {
            from { transform: scale(0.8); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }

        .chip-remove {
            cursor: pointer;
            color: var(--text-dim);
            font-size: 0.95rem;
            line-height: 1;
            padding: 0;
            background: none;
            border: none;
            transition: color 0.15s;
            display: inline-flex;
            align-items: center;
        }

        .chip-remove:hover {
            color: var(--danger);
        }

        #chipInput {
            border: none;
            background: transparent;
            padding: 0.4rem 0.5rem;
            font-size: 0.95rem;
            color: var(--text);
            outline: none;
            font-family: inherit;
            flex: 1;
            min-width: 120px;
        }

        #chipInput::placeholder {
            color: var(--text-dim);
            opacity: 0.5;
        }

        .prompt-counter {
            font-size: 0.75rem;
            color: var(--text-dim);
            text-align: right;
            margin-top: 0.25rem;
            transition: color 0.2s;
        }

        .prompt-counter.warning {
            color: #f59e0b;
        }

        .prompt-counter.danger {
            color: var(--danger);
            font-weight: 600;
        }

        .history-entry.editing {
            flex-direction: column;
            gap: 0.5rem;
        }

        .history-entry .edit-area {
            display: none;
            width: 100%;
        }

        .history-entry.editing .edit-area {
            display: block;
        }

        .history-entry.editing .history-text {
            display: none;
        }

        .history-entry.editing .copy-btn,
        .history-entry.editing .edit-btn {
            display: none;
        }

        .edit-textarea {
            width: 100%;
            background: rgba(0,0,0,0.3);
            border: 1px solid var(--primary);
            border-radius: 8px;
            color: var(--text);
            font-family: inherit;
            font-size: 0.85rem;
            padding: 0.5rem;
            resize: vertical;
            min-height: 3rem;
            outline: none;
        }

        .edit-textarea:focus {
            box-shadow: 0 0 0 2px rgba(56,189,248,0.3);
        }

        .edit-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 0.25rem;
        }

        .edit-actions button {
            padding: 0.3rem 0.8rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 600;
            font-family: inherit;
            transition: all 0.2s;
        }

        .edit-save {
            background: var(--primary);
            color: #000;
        }

        .edit-save:hover {
            filter: brightness(1.15);
        }

        .edit-cancel {
            background: rgba(255,255,255,0.08);
            color: var(--text);
            border: 1px solid var(--border) !important;
        }

        .edit-cancel:hover {
            background: rgba(255,255,255,0.12);
        }

        .edit-btn {
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-dim);
            padding: 0.1rem 0.2rem;
            border-radius: 4px;
            font-size: 0.8rem;
            opacity: 0;
            transition: opacity 0.15s, color 0.2s;
            flex-shrink: 0;
            align-self: center;
            line-height: 1;
        }

        .history-entry:hover .edit-btn {
            opacity: 0.6;
        }

        .edit-btn:hover {
            opacity: 1 !important;
            color: var(--accent);
        }

        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 200;
            backdrop-filter: blur(4px);
        }

        .modal-overlay.visible {
            display: flex;
        }

        .modal-box {
            background: var(--card);
            border-radius: 24px;
            padding: 2rem;
            max-width: 500px;
            width: 90%;
            border: 1px solid var(--border);
            box-shadow: 0 50px 100px -20px rgba(0,0,0,0.7);
            max-height: 80vh;
            overflow-y: auto;
        }

        .modal-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text);
        }

        .modal-desc {
            font-size: 0.85rem;
            color: var(--text-dim);
            margin-bottom: 1.25rem;
            line-height: 1.5;
        }

        .suggestion-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            background: rgba(0,0,0,0.2);
            border-radius: 12px;
            margin-bottom: 0.5rem;
            border: 1px solid var(--border);
        }

        .suggestion-item .arrow {
            color: var(--primary);
            font-weight: 600;
            flex-shrink: 0;
        }

        .suggestion-item .badge {
            background: rgba(79, 70, 229, 0.2);
            color: var(--accent);
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-size: 0.7rem;
            margin-left: 0.3rem;
        }

        .suggestion-item .context-hint {
            font-size: 0.7rem;
            color: var(--text-dim);
            margin-left: 0.3rem;
        }

        .suggestion-item .swap {
            flex: 1;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .suggestion-item .old-val {
            color: var(--danger);
            text-decoration: line-through;
        }

        .suggestion-item .new-val {
            color: var(--success);
        }

        .modal-actions {
            display: flex;
            gap: 0.75rem;
            margin-top: 1.25rem;
            justify-content: flex-end;
        }

        .modal-actions button {
            padding: 0.6rem 1.4rem;
            border-radius: 12px;
            border: none;
            cursor: pointer;
            font-weight: 600;
            font-family: inherit;
            font-size: 0.85rem;
            transition: all 0.2s;
        }

        .modal-accept {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: white;
        }

        .modal-accept:hover {
            filter: brightness(1.1);
            transform: translateY(-1px);
        }

        .modal-skip {
            background: rgba(255,255,255,0.05);
            color: var(--text-dim);
            border: 1px solid var(--border) !important;
        }

        .modal-skip:hover {
            background: rgba(255,255,255,0.1);
        }

        .correction-row {
            display: flex;
            align-items: center;
            gap: 0.6rem;
            padding: 0.5rem 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            font-size: 0.8rem;
        }

        .correction-row:last-child {
            border-bottom: none;
        }

        .correction-row .corr-pattern {
            color: var(--danger);
            min-width: 5rem;
        }

        .correction-row .corr-arrow {
            color: var(--primary);
            flex-shrink: 0;
        }

        .correction-row .corr-replacement {
            color: var(--success);
            flex: 1;
        }

        .correction-row .corr-hits {
            color: var(--text-dim);
            font-size: 0.7rem;
            white-space: nowrap;
        }

        .toggle-switch {
            position: relative;
            width: 32px;
            height: 18px;
            flex-shrink: 0;
        }

        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .toggle-slider {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(255,255,255,0.15);
            border-radius: 18px;
            cursor: pointer;
            transition: background 0.2s;
        }

        .toggle-slider::before {
            content: '';
            position: absolute;
            width: 14px; height: 14px;
            left: 2px; bottom: 2px;
            background: white;
            border-radius: 50%;
            transition: transform 0.2s;
        }

        .toggle-switch input:checked + .toggle-slider {
            background: var(--primary);
        }

        .toggle-switch input:checked + .toggle-slider::before {
            transform: translateX(14px);
        }

        .corr-remove {
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-dim);
            font-size: 1rem;
            padding: 0.1rem 0.3rem;
            border-radius: 4px;
            transition: color 0.15s;
            line-height: 1;
        }

        .corr-remove:hover {
            color: var(--danger);
        }

        .corr-empty {
            color: var(--text-dim);
            padding: 1rem;
            text-align: center;
            font-size: 0.8rem;
        }

        .corr-manual-form {
            display: flex;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            align-items: center;
        }

        .corr-manual-form input {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            padding: 0.4rem 0.6rem;
            border-radius: 8px;
            color: var(--text);
            font-size: 0.8rem;
            font-family: inherit;
            flex: 1;
            min-width: 0;
        }

        .corr-manual-form input:focus {
            outline: none;
            border-color: var(--primary);
        }

        .corr-add-btn {
            background: var(--primary);
            color: #000;
            border: none;
            padding: 0.4rem 0.8rem;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.8rem;
            font-family: inherit;
            white-space: nowrap;
            transition: filter 0.2s;
        }

        .corr-add-btn:hover {
            filter: brightness(1.1);
        }

            @keyframes toastIn {
                from { transform: translateY(20px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }

            .corr-toast {
                position: fixed;
                bottom: 1rem;
                left: 50%;
                transform: translateX(-50%);
                background: var(--success);
                color: #000;
                padding: 0.5rem 1.5rem;
                border-radius: 99px;
                font-weight: 600;
                font-size: 0.85rem;
                box-shadow: 0 10px 30px rgba(74, 222, 128, 0.4);
                z-index: 300;
                animation: toastIn 0.3s ease-out;
                display: none;
            }

            .corr-log-entry {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.4rem 1rem;
                border-bottom: 1px solid rgba(255,255,255,0.04);
                font-size: 0.8rem;
                animation: fadeIn 0.3s forwards;
            }

            .corr-log-entry:last-child {
                border-bottom: none;
            }

            .corr-log-time {
                color: var(--text-dim);
                font-size: 0.7rem;
                white-space: nowrap;
                min-width: 3.5rem;
            }

            .corr-log-old {
                color: var(--danger);
                text-decoration: line-through;
                font-weight: 500;
            }

            .corr-log-arrow {
                color: var(--primary);
            }

            .corr-log-new {
                color: var(--success);
                font-weight: 500;
            }

            .corr-log-badge {
                background: rgba(56,189,248,0.12);
                color: var(--primary);
                padding: 0.1rem 0.4rem;
                border-radius: 4px;
                font-size: 0.65rem;
                margin-left: auto;
                flex-shrink: 0;
            }

            .corr-log-flag {
                background: none;
                border: none;
                cursor: pointer;
                color: var(--text-dim);
                font-size: 0.8rem;
                padding: 0.1rem 0.3rem;
                border-radius: 4px;
                opacity: 0;
                transition: opacity 0.15s, color 0.15s;
                flex-shrink: 0;
            }

            .corr-log-entry:hover .corr-log-flag {
                opacity: 0.6;
            }

            .corr-log-flag:hover {
                opacity: 1 !important;
                color: var(--danger);
            }

            .corr-log-empty {
                color: var(--text-dim);
                padding: 1rem;
                text-align: center;
                font-size: 0.8rem;
            }

            .corr-source-badge {
                font-size: 0.65rem;
                padding: 0.1rem 0.35rem;
                border-radius: 4px;
                flex-shrink: 0;
                font-weight: 600;
            }

            .corr-source-badge.learned {
                background: rgba(129,140,248,0.15);
                color: var(--accent);
            }

            .corr-source-badge.manual {
                background: rgba(251,191,36,0.15);
                color: #fbbf24;
            }

            .corr-context-tag {
                font-size: 0.65rem;
                color: var(--text-dim);
                padding: 0.1rem 0.3rem;
                background: rgba(255,255,255,0.05);
                border-radius: 4px;
                max-width: 120px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex-shrink: 0;
            }

            .corr-last-hit {
                font-size: 0.7rem;
                color: var(--text-dim);
                flex-shrink: 0;
                white-space: nowrap;
            }

            .flag-action-btn {
                padding: 0.5rem 1rem;
                border-radius: 10px;
                border: none;
                cursor: pointer;
                font-weight: 600;
                font-family: inherit;
                font-size: 0.8rem;
                transition: all 0.2s;
                flex: 1;
                text-align: center;
            }

            .flag-action-btn.danger {
                background: rgba(251,113,133,0.15);
                color: var(--danger);
                border: 1px solid rgba(251,113,133,0.3);
            }

            .flag-action-btn.danger:hover {
                background: rgba(251,113,133,0.25);
            }

            .flag-action-btn.warning {
                background: rgba(251,191,36,0.15);
                color: #fbbf24;
                border: 1px solid rgba(251,191,36,0.3);
            }

            .flag-action-btn.warning:hover {
                background: rgba(251,191,36,0.25);
            }

            .flag-detail {
                padding: 0.75rem 1rem;
                background: rgba(0,0,0,0.2);
                border-radius: 10px;
                margin-bottom: 1rem;
                font-size: 0.85rem;
                line-height: 1.6;
            }

            .flag-detail .flag-old {
                color: var(--danger);
                text-decoration: line-through;
            }

            .flag-detail .flag-new {
                color: var(--success);
            }

            .flag-detail .flag-snippet {
                color: var(--text-dim);
                font-style: italic;
            }

            .flag-context-input {
                width: 100%;
                background: rgba(0,0,0,0.2);
                border: 1px solid var(--border);
                padding: 0.5rem 0.75rem;
                border-radius: 8px;
                color: var(--text);
                font-family: inherit;
                font-size: 0.8rem;
                margin-top: 0.25rem;
                outline: none;
            }

            .flag-context-input:focus {
                border-color: var(--primary);
            }

            .volume-slider {
                -webkit-appearance: none;
                width: 100%;
                height: 4px;
                background: rgba(255,255,255,0.12);
                border-radius: 4px;
                outline: none;
            }

            .volume-slider::-webkit-slider-thumb {
                -webkit-appearance: none;
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: var(--primary);
                cursor: pointer;
                box-shadow: 0 0 8px rgba(56,189,248,0.4);
            }

            .volume-slider::-moz-range-thumb {
                width: 16px;
                height: 16px;
                border-radius: 50%;
                background: var(--primary);
                cursor: pointer;
                border: none;
            }

            .volume-label {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 0.5rem;
            }

            .volume-label span {
                font-size: 0.75rem;
                color: var(--text-dim);
                min-width: 2.5rem;
                text-align: right;
            }

            @media (max-width: 600px) {
                .suggestion-item { flex-wrap: wrap; }
                .suggestion-item .swap { width: 100%; }
                .corr-manual-form { flex-wrap: wrap; }
            }
        </style>
</head>
<body>
    <div id="saveBanner" class="save-banner">Settings Saved</div>
    <div class="container">
        <div class="card">
            <div class="header">
                <div>
                    <h1>Voice Typing.</h1>
                    <p class="subtitle">Real-time STT Service</p>
                </div>
                <div id="statusBadge" class="status-badge status-off">
                    <span id="statusText">Disconnected</span>
                </div>
                <button onclick="restartHotkey()" id="hkBtn" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:0.7rem;padding:0.25rem 0.5rem;border-radius:6px;margin-left:0.5rem;" title="Reconnect hotkey after login/sleep">⌨️ Reset</button>
                <button onclick="reinitAudio()" id="reinitBtn" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:0.7rem;padding:0.25rem 0.5rem;border-radius:6px;" title="Reset audio device (fixes mic stuck after call)">🎤 Reinit</button>
            </div>

            <div class="form-section">
                <div class="input-group full-width">
                    <label>Microphone Device</label>
                    <select id="deviceSelect" onchange="autoSave()" title="Select which microphone or audio source to use for voice input. Lists all PulseAudio and ALSA devices detected on the system. If your mic shows as '(audio) ...', it is being routed through PulseAudio for shared access with other applications like calls.">
                        <option value="">Loading devices...</option>
                    </select>
                </div>
                
                <div class="input-group full-width">
                    <label>STT Endpoint</label>
                    <input type="text" id="sttEndpoint" value="{{ stt_endpoint }}" onchange="autoSave()" title="URL of the Speech-to-Text server (must be OpenAI-compatible /v1/audio/transcriptions endpoint). Default points to a local faster-whisper-server. You can use any hosted STT API that follows the OpenAI Whisper API format.">
                </div>

                <div class="input-group full-width">
                    <label>STT API Key</label>
                    <div style="display:flex;gap:0.5rem;">
                        <input type="password" id="sttApiKey" value="{{ stt_api_key }}" placeholder="leave empty for no auth" onchange="autoSave()" style="flex:1;" title="API key for STT endpoint if required (OpenAI, Groq, etc.). Sent as Authorization: Bearer header. Leave empty for local faster-whisper-server which needs no auth. Saved persistently to config.json (plain text).">
                        <button type="button" onclick="toggleSttApiKeyVisibility()" id="toggleSttApiKeyBtn" style="padding:0.5rem 0.85rem;border-radius:10px;background:rgba(255,255,255,0.05);border:1px solid var(--border);color:var(--text-dim);cursor:pointer;" title="Show/hide STT API key">👁</button>
                    </div>
                </div>

                <div class="input-group">
                    <label>STT Model</label>
                    <input type="text" id="sttModel" value="{{ stt_model }}" onchange="autoSave()" title="Model identifier passed to the STT endpoint. For faster-whisper-server, use values like 'Systran/faster-whisper-medium.en' or 'base', 'small', 'medium', 'large-v3'. Larger models are more accurate but slower.">
                </div>

                <div class="input-group">
                    <label>STT Language</label>
                    <select id="sttLanguage" onchange="autoSave()" title="Language for speech-to-text. Auto detects spoken language, or force a specific language to improve accuracy. For Systran/faster-whisper-medium.en only 'en' and 'auto' are valid; for multilingual Systran/faster-whisper-medium any language works. Auto sends no language parameter for auto-detection.">
                        {% for code, name in stt_languages.items() %}
                        <option value="{{ code }}" {% if stt_language == code %}selected{% endif %}>{{ name }} ({{ code }})</option>
                        {% endfor %}
                    </select>
                </div>

                <div class="input-group">
                    <label>Hotkey</label>
                    <input type="text" id="hotkey" value="{{ hotkey }}" onchange="autoSave()" title="Global keyboard shortcut to toggle recording. Uses pynput syntax: <cmd>+<shift>+s, <ctrl>+<alt>+space, etc. The last key is the trigger. After changing the hotkey, the daemon restarts automatically. If the hotkey stops working after login/sleep, use the Reset button.">
                </div>

                <div class="input-group">
                    <label>Mode</label>
                    <select id="streamingMode" onchange="autoSave()" title="Streaming mode transcribes while you speak and types each utterance as soon as silence is detected. Batch mode records the full audio and transcribes once when you stop. Streaming is more responsive but may produce partial sentences. Batch mode is required for LLM post-processing features.">
                        <option value="1" {% if streaming %}selected{% endif %}>Streaming (Real-time)</option>
                        <option value="0" {% if not streaming %}selected{% endif %}>Batch (Once on stop)</option>
                    </select>
                </div>

                <div class="input-group">
                    <label>VAD Threshold</label>
                    <input type="number" step="0.005" id="silenceThreshold" value="{{ silence_threshold }}" onchange="autoSave()" title="Voice Activity Detection sensitivity. Lower values (0.005-0.01) are more sensitive and pick up quieter speech. Higher values (0.02-0.03) require louder input, useful in noisy environments. Adjust if the mic is cutting off or picking up too much background.">
                </div>

                <div class="input-group">
                    <label>Sound Effects</label>
                    <select id="beepEnabled" onchange="autoSave()" title="Play a short beep sound when recording starts (high pitch) and stops (low pitch). Useful for audible feedback that the system heard you. Can be muted if the beeps are distracting.">
                        <option value="1" {% if beep_enabled %}selected{% endif %}>Enabled (Beeps)</option>
                        <option value="0" {% if not beep_enabled %}selected{% endif %}>Muted</option>
                    </select>
                </div>

                <div class="input-group">
                    <label>Beep Volume</label>
                    <div class="volume-label">
                        <input type="range" class="volume-slider" id="beepVolume" min="0" max="100" value="{{ beep_volume * 100 }}" oninput="updateVolumeLabel(this.value); autoSave()" title="Controls the loudness of the start/stop beep sounds independently of system volume. Set to 0% to silence beeps while keeping Sound Effects enabled (useful if you want visual-only indicators).">
                        <span id="volumeLabel">{{ (beep_volume * 100) | round(0) | int }}%</span>
                    </div>
                </div>

                <div class="input-group full-width batch-notice" id="llmNotice" style="display:none;padding:0.6rem 1rem;background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.2);border-radius:10px;color:#fbbf24;font-size:0.8rem;text-align:center;">
                    LLM features require <strong>Batch mode</strong>. Switch above to enable.
                </div>

                <div class="input-group" id="llmActionGroup">
                    <label>LLM Post-Process</label>
                    <select id="llmAction" onchange="onLlmActionChange()" title="Apply an LLM to the transcribed text before output. Grammar Fix cleans punctuation and capitalization. Translate converts to another language. Custom lets you provide any instruction (e.g. 'Summarize', 'Make bullet points'). Requires Batch mode and an OpenAI-compatible LLM endpoint configured below (persistent, overrides .env).">
                        <option value="off">Off</option>
                        <option value="grammar">Grammar Fix</option>
                        <option value="translate">Translate</option>
                        <option value="custom">Custom</option>
                    </select>
                </div>

                <div class="input-group" id="llmLangGroup" style="display:none">
                    <label>Translate Language</label>
                    <select id="llmLang" onchange="autoSave()" title="Target language for the Translate LLM action. The transcribed text will be translated from its original language into the selected language.">
                        <option value="Hindi">Hindi</option>
                        <option value="English">English</option>
                        <option value="French">French</option>
                        <option value="Spanish">Spanish</option>
                        <option value="German">German</option>
                        <option value="Japanese">Japanese</option>
                        <option value="Chinese">Chinese</option>
                        <option value="Arabic">Arabic</option>
                    </select>
                </div>

                <div class="input-group" id="llmCustomGroup" style="display:none">
                    <label>Custom Prompt</label>
                    <input type="text" id="llmCustomPrompt" placeholder="e.g. Convert to bullet points" onchange="autoSave()" title="Your own instruction for the LLM when 'Custom' action is selected. Examples: 'Summarize this in one sentence', 'Format as a to-do list', 'Make this more formal'. The LLM will process the transcribed text according to this instruction.">
                </div>

                <div class="input-group full-width" style="display:flex;gap:0.5rem;align-items:center;margin-top:0.25rem;padding-top:0.75rem;border-top:1px dashed rgba(255,255,255,0.08);">
                    <span style="font-size:0.75rem;font-weight:600;color:var(--accent);text-transform:uppercase;letter-spacing:0.05em;">LLM Credentials (persistent)</span>
                    <span style="font-size:0.7rem;color:var(--text-dim);">— saved to config.json, overrides .env on next load</span>
                </div>

                <div class="input-group">
                    <label>LLM Base URL</label>
                    <input type="text" id="llmBaseUrl" value="{{ openai_base_url }}" placeholder="http://localhost:1234/v1" onchange="autoSave()" title="OpenAI-compatible LLM endpoint base URL. For local LM Studio/Ollama use http://localhost:1234/v1 or http://localhost:11434/v1. Must expose /chat/completions. Saved persistently to config.json.">
                </div>

                <div class="input-group">
                    <label>LLM Model ID</label>
                    <input type="text" id="llmModel" value="{{ openai_chat_model_id }}" placeholder="qwen/qwen3-6b" onchange="autoSave()" title="Model identifier sent to the LLM endpoint as 'model'. For local servers any string your server accepts. For OpenAI use gpt-4o-mini etc. Saved persistently.">
                </div>

                <div class="input-group full-width">
                    <label>LLM API Key</label>
                    <div style="display:flex;gap:0.5rem;">
                        <input type="password" id="llmApiKey" value="{{ openai_api_key }}" placeholder="not-needed for local" onchange="autoSave()" title="API key for the LLM endpoint. For local endpoints often 'not-needed'. For OpenAI use sk-.... Saved persistently to config.json (plain text). Leave empty to keep existing, or clear to remove." style="flex:1;">
                        <button type="button" onclick="toggleApiKeyVisibility()" id="toggleApiKeyBtn" style="padding:0.5rem 0.85rem;border-radius:10px;background:rgba(255,255,255,0.05);border:1px solid var(--border);color:var(--text-dim);cursor:pointer;" title="Show/hide API key">👁</button>
                    </div>
                </div>

                <div class="input-group">
                    <label>Wake Word</label>
                    <input type="text" id="wakeWord" value="{{ wake_word }}" placeholder="chanakya" onchange="autoSave()" title="A special word that, when spoken as the first word of a dictation, triggers command mode. The wake word is stripped from the text and the remainder is sent to the Command URL instead of being typed. Useful for voice-controlled automation (e.g. saying 'chanakya open terminal' sends 'open terminal' to your webhook). Case-insensitive.">
                </div>
                <div class="input-group">
                    <label>Command URL</label>
                    <input type="text" id="commandUrl" value="{{ command_url }}" placeholder="https://ntfy.example.org/" onchange="autoSave()" title="HTTP endpoint that receives wake word commands as raw POST body. When the wake word is detected, the rest of the transcribed text is sent here instead of being typed. Works with ntfy.sh for push notifications, Home Assistant webhooks, or any custom automation endpoint.">
                </div>
                <div class="input-group">
                    <label>Initial Prompt</label>
                    <div class="chip-input" id="chipContainer" title="Words and phrases to bias the STT model toward. Type a word and press Enter or comma to add it as a chip. These are sent as the 'prompt' parameter to the STT API, helping it recognize domain-specific terms, names, and jargon. Natural sentence framing (e.g. 'The following terms are: Kubernetes, gRPC') reduces false positives over bare word lists. Maximum 800 characters.">
                        <div class="chip-list" id="chipList"></div>
                        <input type="text" id="chipInput" placeholder="Type a word and press Enter" autocomplete="off">
                    </div>
                    <div class="prompt-counter" id="promptCounter">0 / 800 characters</div>
                </div>

                <div class="input-group full-width" style="grid-column:span 2;display:flex;gap:1rem;flex-wrap:wrap;">
                    <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;" title="When enabled, you hold the hotkey down to record and release it to stop. Useful for brief dictations where you want precise control over when recording ends. When disabled, the hotkey toggles recording on/off with each press.">
                        <input type="checkbox" id="pushToHold" onchange="autoSave()" {% if push_to_hold %}checked{% endif %}> Push-to-Hold
                    </label>
                    <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;" title="When checked, transcribed text is typed directly into the focused document using xdotool (or clipboard paste as fallback). When unchecked, text is copied to the system clipboard instead of being typed. Uncheck if you only want to paste manually.">
                        <input type="checkbox" id="clipboardMode" onchange="autoSave()" {% if clipboard_mode %}checked{% endif %}> Type into document
                    </label>
                    <label style="display:flex;align-items:center;gap:0.5rem;cursor:pointer;" title="When checked, a BackSpace keystroke is sent immediately after the hotkey is pressed to erase the stray character that some systems inject when the hotkey triggers. If you notice the hotkey deleting a letter from your text, uncheck this. Only relevant for hotkeys that include a letter key like <ctrl>+<shift>+s.">
                        <input type="checkbox" id="backspaceAfterHotkey" onchange="autoSave()" {% if backspace_after_hotkey %}checked{% endif %}> BackSpace after hotkey
                    </label>
                </div>
            </div>

            <div class="controls">
                <button onclick="toggleService()" class="btn-primary" id="toggleBtn" title="Start or stop the voice typing daemon (hotkey listener). When active, the global hotkey will toggle recording. The daemon must be running for hotkey dictation to work. Manual Dictate and Test STT work independently.">Start Daemon</button>
                <button onclick="toggleRecording()" class="btn-secondary" id="recBtn" title="Manually start/stop a recording session without using the hotkey. Useful for testing or when the hotkey is not available. Same as pressing the hotkey once in toggle mode.">Manual Dictate</button>
                <button onclick="toggleMicTest()" class="btn-secondary" id="micTestBtn" title="Open the microphone level meter to test your audio input. Speaks for 5 seconds and shows a real-time level bar. Use this to verify your mic is working and adjust the VAD threshold based on the noise floor.">Test Mic</button>
            </div>

            <div class="preview-box" id="previewBox" style="display:none;margin-top:1rem;padding:0.75rem 1rem;background:rgba(0,0,0,0.25);border-radius:12px;border:1px solid var(--border);font-size:0.9rem;min-height:1.2rem;">
                <span id="previewText" style="color:var(--primary);"></span>
                <span id="previewCursor" style="animation:blink 1s step-end infinite;">▊</span>
            </div>
            <style>
                @keyframes blink { 50% { opacity: 0; } }
            </style>

            <div class="mic-meter" id="micMeter">
                <div class="meter-header">
                    <span class="meter-label">Microphone Level</span>
                    <div class="meter-info">
                        <span class="meter-db" id="meterDb">-inf dB</span>
                        <span class="meter-timer" id="meterTimer">5s</span>
                    </div>
                </div>
                <div class="meter-track" id="meterTrack">
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                    <div class="meter-bar"></div>
                </div>
            </div>

            <div class="stt-test-area">
                <button onclick="testStt()" class="btn-stt" id="sttTestBtn">Test STT Endpoint</button>
                <span></span>
                <div class="stt-result" id="sttResult">
                    <div class="row"><span class="key">Endpoint</span><span class="val" id="sttEndpointVal"></span></div>
                    <div class="row"><span class="key">Model</span><span class="val" id="sttModelVal"></span></div>
                    <div class="row"><span class="key">Time</span><span class="val" id="sttTimeVal"></span></div>
                    <div class="row"><span class="key">Result</span><span class="val" id="sttResultVal"></span></div>
                </div>
            </div>

            <div class="section-header" onclick="toggleHistory()">
                <span class="label">Transcription History</span>
                <span>
                    <a href="/export_history?format=txt" style="color:var(--text-dim);font-size:0.75rem;text-decoration:none;margin-right:0.5rem;" title="Export as TXT" onclick="event.stopPropagation()">⬇ TXT</a>
                    <a href="/export_history?format=md" style="color:var(--text-dim);font-size:0.75rem;text-decoration:none;margin-right:0.75rem;" title="Export as Markdown" onclick="event.stopPropagation()">⬇ MD</a>
                    <span class="count" id="historyCount">0</span> <span class="chevron" id="historyChevron">▶</span>
                </span>
            </div>
            <div class="section-body" id="historyBody">
                <div class="history-entry" style="color:var(--text-dim);padding:1rem;text-align:center">No transcriptions yet</div>
            </div>

            <div class="section-header" onclick="toggleCorrectionLog()">
                <span class="label">Correction Activity</span>
                <span>
                    <span class="count" id="corrLogCount">0</span> <span class="chevron" id="corrLogChevron">▶</span>
                </span>
            </div>
            <div class="section-body" id="corrLogBody">
                <div class="corr-log-empty">No corrections applied yet. Speak something that matches a correction rule.</div>
            </div>

            <div class="section-header" onclick="toggleCorrections()">
                <span class="label">Auto-Corrections</span>
                <span>
                    <span class="count" id="correctionCount">0</span> <span class="chevron" id="correctionChevron">▶</span>
                </span>
            </div>
            <div class="section-body" id="correctionsBody">
                <div class="corr-manual-form">
                    <input type="text" id="corrPatternInput" placeholder="STT says..." onkeydown="if(event.key==='Enter')addManualCorrection()">
                    <span style="color:var(--text-dim);font-size:0.8rem;">→</span>
                    <input type="text" id="corrReplacementInput" placeholder="Should be..." onkeydown="if(event.key==='Enter')addManualCorrection()">
                    <button class="corr-add-btn" onclick="addManualCorrection()">+ Add</button>
                </div>
                <div class="corr-empty" id="corrEmpty">No corrections yet. Edit a transcription below to teach the system.</div>
            </div>

            <div class="modal-overlay" id="suggestionModal">
                <div class="modal-box">
                    <div class="modal-title">Save as Auto-Correction?</div>
                    <div class="modal-desc">I noticed these changes. Saving them lets the system auto-fix the same error next time:</div>
                    <div id="suggestionList"></div>
                    <div class="modal-actions">
                        <button class="modal-skip" onclick="dismissSuggestions()">Skip All</button>
                        <button class="modal-accept" onclick="acceptAllSuggestions()">Accept All</button>
                    </div>
                </div>
            </div>

            <div class="corr-toast" id="corrToast"></div>

            <div class="modal-overlay" id="flagModal">
                <div class="modal-box">
                    <div class="modal-title">Flag Incorrect Correction</div>
                    <div class="modal-desc">This correction was applied but seems wrong. What should we do?</div>
                    <div class="flag-detail" id="flagDetail"></div>
                    <div id="flagActions" style="display:flex;gap:0.75rem;margin-bottom:1rem;"></div>
                    <div id="flagContextSection" style="display:none;margin-bottom:1rem;">
                        <label style="font-size:0.75rem;color:var(--text-dim);font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Only suppress when between these words:</label>
                        <div style="display:flex;gap:0.5rem;margin-top:0.3rem;">
                            <input type="text" class="flag-context-input" id="flagContextLeft" placeholder="Word before" style="flex:1;">
                            <input type="text" class="flag-context-input" id="flagContextRight" placeholder="Word after" style="flex:1;">
                        </div>
                    </div>
                    <div class="modal-actions">
                        <button class="modal-skip" onclick="closeFlagModal()">Cancel</button>
                    </div>
                </div>
            </div>

            <div class="log-container" id="logs">
                <div class="log-entry">Console ready. Monitoring signals...</div>
            </div>
        </div>
    </div>

    <script>
        let isRunning = false;
        let isRecording = false;
        let lastLoggedText = "";
        let initialPromptWords = [];
        let configReady = false;

        function escapeHtml(s) {
            const div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }

        function renderChips() {
            const list = document.getElementById('chipList');
            list.innerHTML = initialPromptWords.map((w, i) =>
                `<span class="chip">${escapeHtml(w)} <button class="chip-remove" onclick="removeChip(${i})" type="button">×</button></span>`
            ).join('');
        }

        function addChip(word) {
            word = word.trim().replace(/,/g, '');
            if (!word) return;
            initialPromptWords.push(word);
            renderChips();
            updatePromptCharCount();
            autoSave();
        }

        function removeChip(index) {
            initialPromptWords.splice(index, 1);
            renderChips();
            updatePromptCharCount();
            autoSave();
        }

        function updatePromptCharCount() {
            const text = initialPromptWords.join(', ');
            const count = text.length;
            const el = document.getElementById('promptCounter');
            el.textContent = count + ' / 800 characters';
            el.classList.toggle('warning', count > 650 && count <= 800);
            el.classList.toggle('danger', count > 800);
        }

        document.addEventListener('DOMContentLoaded', function() {
            const chipInput = document.getElementById('chipInput');
            if (!chipInput) return;

            chipInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault();
                    const val = this.value;
                    if (e.key === ',') {
                        const parts = val.split(',');
                        parts.forEach(p => { const t = p.trim(); if (t) addChip(t); });
                    } else if (val.trim()) {
                        addChip(val);
                    }
                    this.value = '';
                }
                if (e.key === 'Backspace' && this.value === '' && initialPromptWords.length > 0) {
                    removeChip(initialPromptWords.length - 1);
                }
            });

            chipInput.addEventListener('paste', function() {
                setTimeout(() => {
                    const val = this.value;
                    if (val.includes(',')) {
                        const parts = val.split(',');
                        parts.forEach(p => { const t = p.trim(); if (t) addChip(t); });
                        this.value = '';
                    }
                }, 10);
            });
        });

        async function loadDevices() {
            try {
                const res = await fetch('/devices');
                const devices = await res.json();
                const sel = document.getElementById('deviceSelect');
                sel.innerHTML = '';
                const activeIdx = {{ active_device if active_device is not none else -1 }};
                const activePulse = "{{ active_pulse_source or '' }}";
                let hadActive = false;
                devices.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d.index;
                    opt.text = d.name;
                    opt.dataset.pulseSource = d.pulse_source || '';
                    // Match by index and, for PulseAudio devices, by pulse_source to avoid stale 9 -> wrong device
                    const idxMatch = d.index == activeIdx;
                    const pulseMatch = activePulse ? (d.pulse_source || '') === activePulse : true;
                    // For pulse devices sharing the same ALSA index (e.g., all at 7), require pulse_source match
                    const isPulseDevice = !!d.pulse_source;
                    const shouldSelect = isPulseDevice ? (idxMatch && pulseMatch) : idxMatch;
                    // Fallback: if activeIdx is stale 9 (old hardcoded) and pulse matches, select it
                    const isStaleFallback = activeIdx === 9 && activePulse && (d.pulse_source || '') === activePulse;
                    if (shouldSelect || isStaleFallback) { opt.selected = true; hadActive = true; }
                    sel.appendChild(opt);
                });
                if (!hadActive && devices.length > 0) {
                    sel.value = devices[0].index;
                    autoSave();
                }
            } catch (e) { console.error("Device load failed", e); }
        }

        async function updateStatus() {
            try {
                const res = await fetch('/status');
                const data = await res.json();
                
                isRunning = data.is_running;
                isRecording = data.is_recording;

                const badge = document.getElementById('statusBadge');
                const badgeText = document.getElementById('statusText');
                const toggleBtn = document.getElementById('toggleBtn');
                const recBtn = document.getElementById('recBtn');

                if (isRunning) {
                    badge.className = 'status-badge status-on';
                    badgeText.innerText = 'Service Active';
                    toggleBtn.innerText = 'Stop Daemon';
                } else {
                    badge.className = 'status-badge status-off';
                    badgeText.innerText = 'Inactive';
                    toggleBtn.innerText = 'Start Daemon';
                }

                if (isRecording) {
                    recBtn.innerHTML = '<span class="recording-indicator"></span>Listening...';
                    recBtn.className = 'btn-secondary btn-recording';
                } else {
                    recBtn.innerText = 'Manual Dictate';
                    recBtn.className = 'btn-secondary';
                }

                if (data.last_text && data.last_text !== lastLoggedText) {
                    lastLoggedText = data.last_text;
                    addLog(data.last_text);
                }
            } catch (e) {}
        }

        function addLog(text) {
            const container = document.getElementById('logs');
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerText = '>> ' + text;
            container.prepend(entry);
        }

        function getLlmInstruction() {
            const action = document.getElementById('llmAction').value;
            if (action === 'translate') return document.getElementById('llmLang').value;
            if (action === 'custom') return document.getElementById('llmCustomPrompt').value;
            return '';
        }

        function onLlmActionChange() {
            const action = document.getElementById('llmAction').value;
            document.getElementById('llmLangGroup').style.display = action === 'translate' ? '' : 'none';
            document.getElementById('llmCustomGroup').style.display = action === 'custom' ? '' : 'none';
            autoSave();
        }

        function toggleApiKeyVisibility() {
            const inp = document.getElementById('llmApiKey');
            const btn = document.getElementById('toggleApiKeyBtn');
            if (!inp) return;
            if (inp.type === 'password') { inp.type = 'text'; if (btn) btn.textContent = '🙈'; }
            else { inp.type = 'password'; if (btn) btn.textContent = '👁'; }
        }

        function toggleSttApiKeyVisibility() {
            const inp = document.getElementById('sttApiKey');
            const btn = document.getElementById('toggleSttApiKeyBtn');
            if (!inp) return;
            if (inp.type === 'password') { inp.type = 'text'; if (btn) btn.textContent = '🙈'; }
            else { inp.type = 'password'; if (btn) btn.textContent = '👁'; }
        }

        async function autoSave() {
            if (!configReady) return;
            const devSelect = document.getElementById('deviceSelect');
            const devOpt = devSelect.selectedOptions[0];
            const pulseSource = devOpt ? devOpt.dataset.pulseSource || '' : '';
            const sttLangEl = document.getElementById('sttLanguage');
            const sttKeyEl = document.getElementById('sttApiKey');
            const llmBaseEl = document.getElementById('llmBaseUrl');
            const llmModelEl = document.getElementById('llmModel');
            const llmKeyEl = document.getElementById('llmApiKey');
            const settings = {
                stt_endpoint: document.getElementById('sttEndpoint').value,
                stt_model: document.getElementById('sttModel').value,
                stt_language: sttLangEl ? sttLangEl.value : 'auto',
                stt_api_key: sttKeyEl ? sttKeyEl.value : '',
                hotkey: document.getElementById('hotkey').value,
                streaming: document.getElementById('streamingMode').value === "1",
                device_index: devSelect.value,
                pulse_source: pulseSource,
                silence_threshold: document.getElementById('silenceThreshold').value,
                beep_enabled: document.getElementById('beepEnabled').value === "1",
                beep_volume: parseInt(document.getElementById('beepVolume').value) / 100,
                llm_action: document.getElementById('llmAction').value,
                llm_instruction: getLlmInstruction(),
                openai_base_url: llmBaseEl ? llmBaseEl.value : '',
                openai_chat_model_id: llmModelEl ? llmModelEl.value : '',
                openai_api_key: llmKeyEl ? llmKeyEl.value : '',
                push_to_hold: document.getElementById('pushToHold').checked,
                clipboard_mode: document.getElementById('clipboardMode').checked,
                backspace_after_hotkey: document.getElementById('backspaceAfterHotkey').checked,
                wake_word: document.getElementById('wakeWord').value,
                command_url: document.getElementById('commandUrl').value,
                initial_prompt: initialPromptWords.join(', '),
            };

            await fetch('/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            const banner = document.getElementById('saveBanner');
            banner.style.display = 'block';
            setTimeout(() => { banner.style.display = 'none'; }, 2000);
        }

        async function toggleService() {
            await fetch('/toggle_service', {method: 'POST'});
            updateStatus();
        }

        async function toggleRecording() {
            await fetch('/toggle_recording', {method: 'POST'});
            updateStatus();
        }

        async function restartHotkey() {
            const btn = document.getElementById('hkBtn');
            btn.innerText = '⌨️ ...';
            await fetch('/restart_hotkey', {method: 'POST'});
            setTimeout(() => btn.innerText = '⌨️ Reset', 1000);
        }

        async function reinitAudio() {
            const btn = document.getElementById('reinitBtn');
            btn.innerText = '🎤 ...';
            await fetch('/reinit_audio', {method: 'POST'});
            await loadDevices();
            setTimeout(() => btn.innerText = '🎤 Reinit', 1000);
        }

        let micTestActive = false;
        let micTestStartTime = null;
        let micTestInterval = null;

        async function toggleMicTest() {
            if (micTestActive) {
                await stopMicTest();
            } else {
                await startMicTest();
            }
        }

        async function startMicTest() {
            await fetch('/test_mic/start', {method: 'POST'});
            micTestActive = true;
            micTestStartTime = Date.now();
            document.getElementById('micTestBtn').innerText = 'Stop Test';
            document.getElementById('micTestBtn').className = 'btn-primary';
            document.getElementById('micMeter').classList.add('visible');
            micTestInterval = setInterval(updateMeter, 80);
        }

        async function stopMicTest() {
            await fetch('/test_mic/stop', {method: 'POST'});
            micTestActive = false;
            if (micTestInterval) clearInterval(micTestInterval);
            micTestInterval = null;
            document.getElementById('micTestBtn').innerText = 'Test Mic';
            document.getElementById('micTestBtn').className = 'btn-secondary';
            document.getElementById('micMeter').classList.remove('visible');
        }

        async function updateMeter() {
            try {
                const res = await fetch('/test_mic/level');
                const data = await res.json();
                let level = parseFloat(data.level) || 0;
                level = Math.min(1, Math.max(0, level));
                const bars = document.querySelectorAll('.meter-bar');
                const n = bars.length;
                const active = Math.round(level * n);
                bars.forEach((bar, i) => {
                    bar.classList.toggle('lit', i < active);
                    const pct = ((i + 1) / n) * 100;
                    bar.style.height = Math.max(4, pct * 0.7) + '%';
                });

                const dbEl = document.getElementById('meterDb');
                if (level > 0.001) {
                    const db = 20 * Math.log10(level);
                    const dbStr = db.toFixed(1);
                    dbEl.innerText = dbStr + ' dB';
                    dbEl.className = 'meter-db' + (db > -12 ? ' high' : db > -24 ? ' mid' : ' low');
                } else {
                    dbEl.innerText = '-inf dB';
                    dbEl.className = 'meter-db low';
                }

                const elapsed = (Date.now() - micTestStartTime) / 1000;
                const remaining = Math.max(0, 5 - elapsed);
                document.getElementById('meterTimer').innerText = Math.ceil(remaining) + 's';
                if (remaining <= 0) await stopMicTest();
            } catch (e) {}
        }

        let historyOpen = false;

        function toggleHistory() {
            historyOpen = !historyOpen;
            document.getElementById('historyBody').classList.toggle('open', historyOpen);
            document.getElementById('historyChevron').classList.toggle('open', historyOpen);
        }

        async function updateHistory() {
            try {
                const res = await fetch('/history');
                const entries = await res.json();
                document.getElementById('historyCount').innerText = entries.length;
                const body = document.getElementById('historyBody');
                if (!entries.length) {
                    body.innerHTML = '<div class="history-entry" style="color:var(--text-dim);padding:1rem;text-align:center">No transcriptions yet</div>';
                    return;
                }
                const allEntries = entries.slice().reverse();
                body.innerHTML = allEntries.map((e, i) => {
                    const realIdx = entries.length - 1 - i;
                    return '<div class="history-entry" id="he-' + realIdx + '">' +
                        '<span class="history-dot ' + e.source + '"></span>' +
                        '<span class="history-time">' + e.time + '</span>' +
                        '<span class="history-text">' + escapeHtml(e.text) + '</span>' +
                        '<button class="edit-btn" onclick="event.stopPropagation(); editHistoryEntry(' + realIdx + ')" title="Edit text">✏️</button>' +
                        '<button class="copy-btn' + (i === 0 ? ' visible' : '') + '" onclick="event.stopPropagation(); copyHistoryText(this.parentElement)" title="Copy text">📋</button>' +
                        '<div class="edit-area"></div>' +
                        '</div>';
                }).join('');
            } catch (e) {}
        }

        function copyHistoryText(entry) {
            const text = entry.querySelector('.history-text').textContent;
            const btn = entry.querySelector('.copy-btn');
            navigator.clipboard.writeText(text).then(() => {
                if (btn) {
                    btn.textContent = '✓';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.textContent = '📋';
                        btn.classList.remove('copied');
                    }, 1500);
                }
            }).catch(() => {});
        }

        /* ── Correction / Edit Functions ── */

        let pendingSuggestions = [];

        function editHistoryEntry(index) {
            const entry = document.getElementById('he-' + index);
            if (!entry) return;
            const textEl = entry.querySelector('.history-text');
            const areaEl = entry.querySelector('.edit-area');
            const originalText = textEl.textContent;
            areaEl.innerHTML =
                '<textarea class="edit-textarea" id="edit-ta-' + index + '">' + escapeHtml(originalText) + '</textarea>' +
                '<div class="edit-actions">' +
                '<button class="edit-save" onclick="saveHistoryEdit(' + index + ')">Save</button>' +
                '<button class="edit-cancel" onclick="cancelHistoryEdit(' + index + ')">Cancel</button>' +
                '</div>';
            entry.classList.add('editing');
            const ta = document.getElementById('edit-ta-' + index);
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);
        }

        function cancelHistoryEdit(index) {
            const entry = document.getElementById('he-' + index);
            if (entry) entry.classList.remove('editing');
        }

        async function saveHistoryEdit(index) {
            const entry = document.getElementById('he-' + index);
            if (!entry) return;
            const newText = document.getElementById('edit-ta-' + index).value;
            entry.classList.remove('editing');
            if (!newText.trim()) return;
            try {
                const res = await fetch('/history/correct', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({index: index, new_text: newText.trim()})
                });
                const data = await res.json();
                if (data.success && data.changed && data.suggestions && data.suggestions.length > 0) {
                    pendingSuggestions = data.suggestions.map(s => ({...s, accepted: false, index: index}));
                    showSuggestionModal();
                }
            } catch (e) {
                console.error('Save history edit failed', e);
            }
        }

        function showSuggestionModal() {
            if (!pendingSuggestions.length) return;
            const list = document.getElementById('suggestionList');
            list.innerHTML = pendingSuggestions.map((s, i) => {
                let ctxHtml = '';
                if (s.context_left || s.context_right) {
                    ctxHtml = '<span class="context-hint">(around "' + escapeHtml(s.context_left) + ' … ' + escapeHtml(s.context_right) + '")</span>';
                }
                return '<div class="suggestion-item" data-idx="' + i + '">' +
                    '<div class="swap">' +
                    '<span class="old-val">' + escapeHtml(s.pattern) + '</span>' +
                    '<span class="arrow">→</span>' +
                    '<span class="new-val">' + escapeHtml(s.replacement) + '</span>' +
                    ctxHtml +
                    '</div>' +
                    '<label class="toggle-switch" title="Include context to reduce false positives">' +
                    '<input type="checkbox" class="suggestion-ctx" checked data-idx="' + i + '">' +
                    '<span class="toggle-slider"></span>' +
                    '</label>' +
                    '<span class="badge" title="When checked, only correct when surrounded by the detected words">ctx</span>' +
                    '</div>';
            }).join('');
            document.getElementById('suggestionModal').classList.add('visible');
        }

        async function acceptAllSuggestions() {
            const toggles = document.querySelectorAll('.suggestion-ctx');
            toggles.forEach(t => {
                const idx = parseInt(t.dataset.idx);
                if (idx >= 0 && idx < pendingSuggestions.length) {
                    pendingSuggestions[idx].useContext = t.checked;
                }
            });
            let count = 0;
            for (const s of pendingSuggestions) {
                const body = {
                    pattern: s.pattern,
                    replacement: s.replacement,
                    source: 'learned',
                };
                if (s.useContext) {
                    body.context_left = s.context_left || '';
                    body.context_right = s.context_right || '';
                }
                try {
                    const res = await fetch('/corrections', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(body)
                    });
                    const data = await res.json();
                    if (data.success) count++;
                } catch (e) {
                    console.error('Save correction failed', e);
                }
            }
            dismissSuggestions();
            showCorrToast('Saved ' + count + ' correction' + (count !== 1 ? 's' : ''));
            loadCorrections();
        }

        function dismissSuggestions() {
            document.getElementById('suggestionModal').classList.remove('visible');
            pendingSuggestions = [];
        }

        function showCorrToast(msg) {
            const el = document.getElementById('corrToast');
            el.textContent = msg;
            el.style.display = 'block';
            setTimeout(() => { el.style.display = 'none'; }, 3000);
        }

        let correctionsOpen = false;

        function toggleCorrections() {
            correctionsOpen = !correctionsOpen;
            document.getElementById('correctionsBody').classList.toggle('open', correctionsOpen);
            document.getElementById('correctionChevron').classList.toggle('open', correctionsOpen);
            if (correctionsOpen) loadCorrections();
        }

        async function loadCorrections() {
            try {
                const res = await fetch('/corrections');
                const corrs = await res.json();
                document.getElementById('correctionCount').innerText = corrs.length;
                const body = document.getElementById('correctionsBody');
                const empty = document.getElementById('corrEmpty');
                if (!corrs.length) {
                    empty.style.display = 'block';
                    return;
                }
                empty.style.display = 'none';
                let html = '';
                corrs.forEach(c => {
                    const ctx = (c.context_left || c.context_right)
                        ? escapeHtml(c.context_left || '…') + ' … ' + escapeHtml(c.context_right || '…')
                        : '';
                    const excCount = (c.exceptions || []).length;
                    const lastHit = c.last_hit
                        ? timeAgo(c.last_hit)
                        : '';
                    html +=
                        '<div class="correction-row" data-cid="' + c.id + '">' +
                        '<label class="toggle-switch">' +
                        '<input type="checkbox" class="corr-toggle" ' + (c.enabled ? 'checked' : '') + '>' +
                        '<span class="toggle-slider"></span>' +
                        '</label>' +
                        '<span class="corr-pattern">' + escapeHtml(c.pattern) + '</span>' +
                        '<span class="corr-arrow">→</span>' +
                        '<span class="corr-replacement">' + escapeHtml(c.replacement) + '</span>' +
                        '<span class="corr-source-badge ' + (c.source || 'manual') + '">' + (c.source || 'manual') + '</span>' +
                        '<span class="corr-hits" title="Times applied">' + (c.hits || 0) + '\u00d7</span>' +
                        (lastHit ? '<span class="corr-last-hit" title="Last triggered">' + lastHit + '</span>' : '') +
                        (ctx ? '<span class="corr-context-tag" title="Context: ' + ctx + '">ctx</span>' : '') +
                        (excCount ? '<span class="badge" style="background:rgba(251,113,133,0.15);color:var(--danger);" title="' + excCount + ' exception(s)">!' + excCount + '</span>' : '') +
                        '<button class="corr-remove" title="Delete">\u00d7</button>' +
                        '</div>';
                });
                const form = body.querySelector('.corr-manual-form');
                const existing = body.querySelectorAll('.correction-row');
                existing.forEach(function(el) { el.remove(); });
                if (form) form.insertAdjacentHTML('afterend', html);
            } catch (e) {
                console.error('Load corrections failed', e);
            }
        }

        function timeAgo(ts) {
            if (!ts) return '';
            var diff = Math.floor((Date.now() / 1000) - ts);
            if (diff < 60) return 'now';
            if (diff < 3600) return Math.floor(diff / 60) + 'm';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h';
            return Math.floor(diff / 86400) + 'd';
        }

        async function toggleCorrection(id, enabled) {
            await fetch('/corrections/' + id, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled: enabled})
            });
        }

        async function deleteCorrection(id) {
            const res = await fetch('/corrections/' + id, {method: 'DELETE'});
            const data = await res.json();
            if (data.success) {
                showCorrToast('Correction deleted');
                loadCorrections();
            }
        }

        document.addEventListener('change', function(e) {
            if (e.target.classList.contains('corr-toggle')) {
                const row = e.target.closest('.correction-row');
                if (row) toggleCorrection(row.dataset.cid, e.target.checked);
            }
        });

        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('corr-remove')) {
                const row = e.target.closest('.correction-row');
                if (row) deleteCorrection(row.dataset.cid);
            }
        });

        async function addManualCorrection() {
            const pattern = document.getElementById('corrPatternInput').value.trim();
            const replacement = document.getElementById('corrReplacementInput').value.trim();
            if (!pattern || !replacement) return;
            const res = await fetch('/corrections', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({pattern: pattern, replacement: replacement, source: 'manual'})
            });
            const data = await res.json();
            if (data.success) {
                document.getElementById('corrPatternInput').value = '';
                document.getElementById('corrReplacementInput').value = '';
                showCorrToast('Correction added');
                loadCorrections();
            } else {
                showCorrToast('Error: ' + (data.errors || ['Unknown']).join(', '));
            }
        }

        function updateVolumeLabel(val) {
            const el = document.getElementById('volumeLabel');
            if (el) el.textContent = val + '%';
        }

        let corrLogOpen = false;

        function toggleCorrectionLog() {
            corrLogOpen = !corrLogOpen;
            document.getElementById('corrLogBody').classList.toggle('open', corrLogOpen);
            document.getElementById('corrLogChevron').classList.toggle('open', corrLogOpen);
            if (corrLogOpen) loadCorrectionLog();
        }

        async function loadCorrectionLog() {
            try {
                const res = await fetch('/correction_log');
                const entries = await res.json();
                document.getElementById('corrLogCount').innerText = entries.length;
                const body = document.getElementById('corrLogBody');
                if (!entries.length) {
                    body.innerHTML = '<div class="corr-log-empty">No corrections applied yet.</div>';
                    return;
                }
                body.innerHTML = entries.slice().reverse().map(e =>
                    '<div class="corr-log-entry" data-cid="' + escapeHtml(e.corr_id || '') + '">' +
                    '<span class="corr-log-time">' + escapeHtml(e.time) + '</span>' +
                    '<span class="corr-log-old">' + escapeHtml(e.pattern) + '</span>' +
                    '<span class="corr-log-arrow">→</span>' +
                    '<span class="corr-log-new">' + escapeHtml(e.replacement) + '</span>' +
                    '<span class="corr-log-badge">corrected</span>' +
                    '<button class="corr-log-flag" onclick="showFlagModal(this.parentElement)" title="Flag as incorrect">⚠</button>' +
                    '</div>'
                ).join('');
            } catch (e) {
                console.error('Load correction log failed', e);
            }
        }

        function showFlagModal(entryEl) {
            const corrId = entryEl.dataset.cid || '';
            const pattern = entryEl.querySelector('.corr-log-old').textContent;
            const replacement = entryEl.querySelector('.corr-log-new').textContent;
            document.getElementById('flagDetail').innerHTML =
                'Correction: <span class="flag-old">' + escapeHtml(pattern) + '</span> ' +
                '<span class="flag-arrow">→</span> <span class="flag-new">' + escapeHtml(replacement) + '</span>' +
                '<br><span class="flag-snippet">in: &quot;' + escapeHtml(entryEl.querySelector('.corr-log-badge').textContent) + '&quot;</span>';
            document.getElementById('flagContextSection').style.display = 'none';
            document.getElementById('flagContextLeft').value = '';
            document.getElementById('flagContextRight').value = '';
            document.getElementById('flagModal').classList.add('visible');
            document.querySelector('#flagModal .modal-title').textContent = 'Flag Incorrect Correction';
            document.querySelector('#flagModal .modal-desc').textContent = 'This correction was applied but seems wrong. What should we do?';
            const btns = document.getElementById('flagActions');
            if (btns) {
                btns.innerHTML =
                    '<button class="flag-action-btn danger" data-flag-action="disable" data-cid="' + corrId + '">Disable This Rule</button>' +
                    '<button class="flag-action-btn warning" data-flag-action="add_exception" data-cid="' + corrId + '">Add Context Exception</button>';
            }
        }

        function closeFlagModal() {
            document.getElementById('flagModal').classList.remove('visible');
        }

        document.addEventListener('click', function(e) {
            var btn = e.target.closest('[data-flag-action]');
            if (!btn) return;
            var action = btn.dataset.flagAction;
            var corrId = btn.dataset.cid;
            if (action === 'confirm_exception') {
                submitFlagException(corrId);
            } else if (action === 'close') {
                closeFlagModal();
            } else {
                flagCorrection(action, corrId);
            }
        });

        async function flagCorrection(action, corrId) {
            if (action === 'disable') {
                const res = await fetch('/corrections/' + corrId + '/flag', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action: 'disable'})
                });
                const data = await res.json();
                closeFlagModal();
                if (data.success) {
                    showCorrToast('Correction rule disabled');
                    loadCorrections();
                } else {
                    showCorrToast('Error: ' + (data.error || 'unknown'));
                }
            } else if (action === 'add_exception') {
                document.getElementById('flagContextSection').style.display = 'block';
                const btns = document.getElementById('flagActions');
                if (btns) {
                    btns.innerHTML =
                        '<button class="flag-action-btn warning" data-flag-action="confirm_exception" data-cid="' + corrId + '">Confirm Exception</button>' +
                        '<button class="modal-skip" data-flag-action="close" style="flex:1">Cancel</button>';
                }
            }
        }

        async function submitFlagException(corrId) {
            const left = document.getElementById('flagContextLeft').value.trim();
            const right = document.getElementById('flagContextRight').value.trim();
            if (!left && !right) {
                showCorrToast('Enter at least one context word');
                return;
            }
            const res = await fetch('/corrections/' + corrId + '/flag', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'add_exception', context_left: left, context_right: right})
            });
            const data = await res.json();
            closeFlagModal();
            if (data.success) {
                showCorrToast('Exception added. Correction will not fire in this context.');
                loadCorrections();
            } else {
                showCorrToast('Error: ' + (data.error || 'unknown'));
            }
        }

        async function testStt() {
            const btn = document.getElementById('sttTestBtn');
            btn.disabled = true;
            btn.innerText = 'Recording for 2s...';
            const resultEl = document.getElementById('sttResult');
            resultEl.classList.remove('visible');
            try {
                const res = await fetch('/test_stt', {method: 'POST'});
                const data = await res.json();
                document.getElementById('sttEndpointVal').innerText = data.endpoint;
                document.getElementById('sttModelVal').innerText = data.model;
                if (data.success) {
                    document.getElementById('sttTimeVal').innerHTML = '<span class="val success">' + data.elapsed + 's</span>';
                    document.getElementById('sttResultVal').innerHTML = '<span class="val success">' + escapeHtml(data.text) + '</span>';
                } else {
                    document.getElementById('sttTimeVal').innerHTML = '<span class="val fail">—</span>';
                    document.getElementById('sttResultVal').innerHTML = '<span class="val fail">' + escapeHtml(data.error) + '</span>';
                }
                resultEl.classList.add('visible');
            } catch (e) {
                document.getElementById('sttEndpointVal').innerText = '—';
                document.getElementById('sttModelVal').innerText = '—';
                document.getElementById('sttTimeVal').innerHTML = '<span class="val fail">—</span>';
                document.getElementById('sttResultVal').innerHTML = '<span class="val fail">' + e.message + '</span>';
                resultEl.classList.add('visible');
            }
            btn.disabled = false;
            btn.innerText = 'Test STT Endpoint';
        }

        async function loadLlmConfig() {
            try {
                const res = await fetch('/llm_config');
                const data = await res.json();
                document.getElementById('llmAction').value = data.llm_action || 'off';
                document.getElementById('pushToHold').checked = data.push_to_hold || false;
                document.getElementById('clipboardMode').checked = data.clipboard_mode !== false;
                const langSel = document.getElementById('llmLang');
                if (data.llm_instruction && langSel.querySelector('option[value="' + data.llm_instruction + '"]')) {
                    langSel.value = data.llm_instruction;
                }
                document.getElementById('llmCustomPrompt').value = (data.llm_action === 'custom' ? data.llm_instruction : '') || '';
                document.getElementById('wakeWord').value = data.wake_word || 'chanakya';
                document.getElementById('commandUrl').value = data.command_url || '';
                // persistent LLM credentials
                if (document.getElementById('llmBaseUrl')) document.getElementById('llmBaseUrl').value = data.openai_base_url || '';
                if (document.getElementById('llmModel')) document.getElementById('llmModel').value = data.openai_chat_model_id || '';
                if (document.getElementById('llmApiKey')) document.getElementById('llmApiKey').value = data.openai_api_key || '';
                // STT language + API key (also via /llm_config for tray compat)
                const sttLangSel = document.getElementById('sttLanguage');
                if (sttLangSel && data.stt_language) sttLangSel.value = data.stt_language;
                else if (sttLangSel && data.stt_language === undefined) {
                    // fallback: fetch /config if needed
                }
                if (document.getElementById('sttApiKey')) document.getElementById('sttApiKey').value = data.stt_api_key || data.sttApiKey || '';
                initialPromptWords = (data.initial_prompt || '').split(',').map(w => w.trim()).filter(w => w);
                renderChips();
                updatePromptCharCount();
                onLlmActionChange();
                configReady = true;
            } catch (e) { configReady = true; }
        }

        let lastPreviewText = '';

        async function updatePreview() {
            try {
                const res = await fetch('/status');
                const data = await res.json();
                const box = document.getElementById('previewBox');
                const el = document.getElementById('previewText');
                if (data.is_recording && data.last_text && data.last_text !== lastPreviewText) {
                    box.style.display = 'block';
                    el.innerText = data.last_text;
                    lastPreviewText = data.last_text;
                    box.scrollIntoView({behavior: 'smooth', block: 'nearest'});
                }
            } catch (e) {}
        }

        loadLlmConfig().then ? null : null;
        loadDevices();
        loadCorrections();
        setInterval(updateStatus, 1000);
        setInterval(updateHistory, 2000);
        setInterval(updatePreview, 500);
        setInterval(function() { if (correctionsOpen) loadCorrections(); }, 10000);
        setInterval(function() { if (corrLogOpen) loadCorrectionLog(); }, 3000);
        updateStatus();
        updateHistory();
        loadCorrectionLog();
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE,
        stt_endpoint=voice_dictation.STT_ENDPOINT,
        stt_model=voice_dictation.STT_MODEL,
        stt_language=voice_dictation.STT_LANGUAGE,
        stt_api_key=voice_dictation.STT_API_KEY,
        stt_languages=voice_dictation.STT_LANGUAGES,
        streaming=voice_dictation.STREAMING_MODE,
        hotkey=voice_dictation.HOTKEY_STR,
        active_device=voice_dictation.DEVICE_INDEX,
        active_pulse_source=voice_dictation.PULSE_SOURCE_NAME,
        silence_threshold=voice_dictation.SILENCE_THRESHOLD,
        beep_enabled=voice_dictation.BEEP_ENABLED,
        beep_volume=voice_dictation.BEEP_VOLUME,
        push_to_hold=dict_app.push_to_hold,
        clipboard_mode=dict_app.clipboard_mode,
        backspace_after_hotkey=voice_dictation.BACKSPACE_AFTER_HOTKEY,
        openai_base_url=voice_dictation.OPENAI_BASE_URL,
        openai_chat_model_id=voice_dictation.OPENAI_CHAT_MODEL_ID,
        openai_api_key=voice_dictation.OPENAI_API_KEY,
        wake_word=voice_dictation.WAKE_WORD,
        command_url=voice_dictation.COMMAND_URL,
        initial_prompt=voice_dictation.INITIAL_PROMPT,
    )


@app.route("/devices")
def get_devices():
    return jsonify(dict_app.recorder.get_input_devices())


@app.route("/settings", methods=["POST"])
def save_settings():
    data = request.json
    dict_app.update_config(
        stt_endpoint=data.get("stt_endpoint"),
        stt_model=data.get("stt_model"),
        stt_language=data.get("stt_language"),
        stt_api_key=data.get("stt_api_key"),
        streaming=data.get("streaming"),
        hotkey=data.get("hotkey"),
        device_index=data.get("device_index"),
        silence_threshold=data.get("silence_threshold"),
        beep_enabled=data.get("beep_enabled"),
        beep_volume=data.get("beep_volume"),
        pulse_source=data.get("pulse_source"),
        push_to_hold=data.get("push_to_hold"),
        clipboard_mode=data.get("clipboard_mode"),
        backspace_after_hotkey=data.get("backspace_after_hotkey"),
        llm_action=data.get("llm_action"),
        llm_instruction=data.get("llm_instruction"),
        openai_base_url=data.get("openai_base_url"),
        openai_chat_model_id=data.get("openai_chat_model_id"),
        openai_api_key=data.get("openai_api_key"),
        wake_word=data.get("wake_word"),
        command_url=data.get("command_url"),
        initial_prompt=data.get("initial_prompt"),
    )
    return jsonify({"success": True})


@app.route("/status")
def get_status():
    return jsonify(
        {
            "is_running": dict_app.is_running,
            "is_recording": dict_app.is_recording,
            "last_text": dict_app.last_transcription,
            "status": dict_app.status,
        }
    )


@app.route("/toggle_service", methods=["POST"])
def toggle_service():
    if dict_app.is_running:
        dict_app.stop_service()
    else:
        dict_app.start_service()
    return jsonify({"success": True})


@app.route("/toggle_recording", methods=["POST"])
def toggle_recording():
    if not dict_app.is_running:
        dict_app.start_service()
    dict_app.toggle_recording()
    return jsonify({"success": True})


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/test_mic/start", methods=["POST"])
def start_mic_test():
    dict_app.start_mic_test()
    return jsonify({"success": True})


@app.route("/test_mic/stop", methods=["POST"])
def stop_mic_test():
    dict_app.stop_mic_test()
    return jsonify({"success": True})


@app.route("/test_mic/level")
def mic_test_level():
    return jsonify({"level": dict_app.get_mic_test_level()})


@app.route("/history")
def get_history():
    return jsonify(dict_app.transcription_history)


@app.route("/test_stt", methods=["POST"])
def test_stt():
    return jsonify(dict_app.test_stt_endpoint())


@app.route("/llm_config", methods=["GET", "POST"])
def llm_config():
    if request.method == "POST":
        data = request.json
        # Persist via update_config so config.json is updated (tray compat)
        dict_app.update_config(
            openai_base_url=data.get("openai_base_url"),
            openai_chat_model_id=data.get("openai_chat_model_id"),
            openai_api_key=data.get("openai_api_key"),
            llm_action=data.get("llm_action"),
            llm_instruction=data.get("llm_instruction"),
            stt_language=data.get("stt_language"),
            stt_api_key=data.get("stt_api_key", data.get("sttApiKey")),
            push_to_hold=data.get("push_to_hold"),
            clipboard_mode=data.get("clipboard_mode"),
            wake_word=data.get("wake_word"),
            command_url=data.get("command_url"),
            initial_prompt=data.get("initial_prompt"),
        )
        # Also allow tray to update only subset without overwriting others with None
        # update_config already handles None = no change, so safe
        return jsonify({"success": True})
    import voice_dictation as vd
    return jsonify({
        "openai_base_url": vd.OPENAI_BASE_URL,
        "openai_chat_model_id": vd.OPENAI_CHAT_MODEL_ID,
        "openai_api_key": vd.OPENAI_API_KEY,
        "stt_api_key": vd.STT_API_KEY,
        "stt_language": vd.STT_LANGUAGE,
        "llm_action": dict_app.llm_action,
        "llm_instruction": dict_app.llm_instruction,
        "push_to_hold": dict_app.push_to_hold,
        "clipboard_mode": dict_app.clipboard_mode,
        "wake_word": dict_app.wake_word,
        "command_url": dict_app.command_url,
        "initial_prompt": dict_app.initial_prompt,
    })


@app.route("/export_history")
def export_history():
    fmt = request.args.get("format", "txt")
    lines = [f"[{e['time']}] {e['text']}" for e in dict_app.transcription_history]
    text = "\n".join(lines) if lines else "No transcriptions yet."
    ext = "txt"
    if fmt == "md":
        text = "# Transcription History\n\n" + "\n".join(
            f"- **{e['time']}** {e['text']}" for e in dict_app.transcription_history
        )
        ext = "md"
    return Response(
        text,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=transcriptions.{ext}"},
    )


@app.route("/restart_hotkey", methods=["POST"])
def restart_hotkey():
    dict_app.restart_hotkey()
    return jsonify({"success": True})


@app.route("/copy_to_clipboard", methods=["POST"])
def copy_to_clipboard():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"success": False, "error": "missing text"}), 400
    dict_app.copy_to_clipboard(text)
    return jsonify({"success": True})


@app.route("/reinit_audio", methods=["POST"])
def reinit_audio():
    dict_app.reinit_audio()
    return jsonify({"success": True})


@app.route("/corrections", methods=["GET"])
def get_corrections():
    return jsonify(dict_app.get_corrections())


@app.route("/corrections", methods=["POST"])
def add_correction():
    data = request.json
    result = dict_app.add_correction(
        pattern=data.get("pattern", ""),
        replacement=data.get("replacement", ""),
        source=data.get("source", "manual"),
        context_left=data.get("context_left", ""),
        context_right=data.get("context_right", ""),
    )
    status = 400 if not result.get("success") else 201
    return jsonify(result), status


@app.route("/corrections/<corr_id>", methods=["PUT"])
def update_correction(corr_id):
    result = dict_app.update_correction(corr_id, request.json)
    status = 404 if not result.get("success") else 200
    return jsonify(result), status


@app.route("/corrections/<corr_id>", methods=["DELETE"])
def delete_correction(corr_id):
    result = dict_app.remove_correction(corr_id)
    status = 404 if not result.get("success") else 200
    return jsonify(result), status


@app.route("/history/correct", methods=["POST"])
def correct_history():
    data = request.json
    index = data.get("index")
    new_text = data.get("new_text", "")
    if index is None:
        return jsonify({"success": False, "error": "Missing index"}), 400
    result = dict_app.correct_history_entry(int(index), new_text)
    status = 404 if not result.get("success") else 200
    return jsonify(result), status


@app.route("/correction_log")
def get_correction_log():
    return jsonify(dict_app.get_correction_log())


@app.route("/corrections/<corr_id>/flag", methods=["POST"])
def flag_correction(corr_id):
    data = request.json
    result = dict_app.flag_incorrect(
        corr_id,
        action=data.get("action", "disable"),
        context_left=data.get("context_left", ""),
        context_right=data.get("context_right", ""),
    )
    status = 404 if not result.get("success") else 200
    return jsonify(result), status


if __name__ == "__main__":
    dict_app.start_service()
    try:
        _tray_env = os.environ.copy()
        for _k in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"):
            if _k not in _tray_env:
                _tray_env[_k] = ""
        subprocess.Popen(
            ["/usr/bin/python3", os.path.join(os.path.dirname(__file__), "tray.py")],
            env=_tray_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    app.run(host=_ui_host, port=_ui_port)
