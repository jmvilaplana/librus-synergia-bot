"""
Panel de control web moderno para el bot de Librus (Srta. Rottenmeier).
Integra diseño en 3 columnas para los hijos, avatar oficial, modales detallados (horarios, notas, mensajes)
y enlaces interactivos totalmente operativos.
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime
from aiohttp import web
import db


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Srta. Rottenmeier - Panel Escolar</title>
    <style>
        :root {
            --bg-color: #0b1120;
            --card-bg: rgba(23, 32, 51, 0.78);
            --card-bg-elevated: rgba(30, 41, 59, 0.88);
            --border-color: rgba(255, 255, 255, 0.09);
            --border-hover: rgba(56, 189, 248, 0.45);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent: #38bdf8;
            --accent-hover: #0284c7;
            --accent-gold: #fbbf24;
            --accent-green: #34d399;
            --accent-red: #f87171;
            --accent-purple: #c084fc;
            --card-radius: 16px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        body {
            background-color: var(--bg-color);
            background-image: radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.09) 0px, transparent 40%),
                              radial-gradient(at 100% 0%, rgba(192, 132, 252, 0.07) 0px, transparent 40%),
                              radial-gradient(at 50% 100%, rgba(15, 23, 42, 0.85) 0px, transparent 60%);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px 16px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Top Bar */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--card-bg);
            backdrop-filter: blur(14px);
            border: 1px solid var(--border-color);
            padding: 14px 22px;
            border-radius: var(--card-radius);
            box-shadow: 0 4px 25px rgba(0, 0, 0, 0.35);
            flex-wrap: wrap;
            gap: 12px;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .avatar-wrap {
            position: relative;
            width: 52px;
            height: 52px;
            border-radius: 50%;
            overflow: hidden;
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.4), 0 4px 12px rgba(0, 0, 0, 0.4);
            flex-shrink: 0;
            background: #1e293b;
        }

        .avatar-wrap img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .brand-title h1 {
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .brand-title p {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .brand-title p a {
            color: var(--accent);
            text-decoration: none;
            font-weight: 600;
            transition: color 0.2s;
        }

        .brand-title p a:hover {
            color: #ffffff;
            text-decoration: underline;
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .badge-status {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 600;
            background: rgba(16, 185, 129, 0.12);
            color: var(--accent-green);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .status-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.3; }
            100% { opacity: 1; }
        }

        button.btn {
            background: var(--accent);
            color: #0b1120;
            font-weight: 600;
            border: none;
            border-radius: 10px;
            padding: 8px 14px;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        button.btn:hover {
            background: var(--accent-hover);
            color: #ffffff;
            transform: translateY(-1px);
        }

        button.btn-secondary {
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        button.btn-secondary:hover {
            background: rgba(255, 255, 255, 0.14);
            border-color: var(--border-hover);
        }

        /* Banner informativo */
        .info-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: var(--text-muted);
            padding: 0 6px;
        }

        .info-bar a {
            color: var(--accent);
            text-decoration: none;
        }

        .info-bar a:hover {
            text-decoration: underline;
        }

        /* 3 Columns Layout */
        .pupils-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }

        @media (max-width: 1050px) {
            .pupils-grid {
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            }
        }

        .pupil-col {
            background: var(--card-bg);
            backdrop-filter: blur(14px);
            border: 1px solid var(--border-color);
            border-radius: var(--card-radius);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: transform 0.2s, border-color 0.2s;
        }

        .pupil-col:hover {
            border-color: var(--border-hover);
        }

        .col-header {
            background: linear-gradient(180deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.6) 100%);
            border-bottom: 1px solid var(--border-color);
            padding: 16px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .col-title {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .col-icon {
            font-size: 26px;
        }

        .col-name {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .col-user {
            font-size: 0.72rem;
            color: var(--text-muted);
        }

        .col-user a {
            color: var(--text-secondary);
            text-decoration: none;
            transition: color 0.2s;
        }

        .col-user a:hover {
            color: var(--accent);
            text-decoration: underline;
        }

        .overall-badge {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            background: rgba(251, 191, 36, 0.12);
            border: 1px solid rgba(251, 191, 36, 0.35);
            padding: 4px 10px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .overall-badge:hover {
            background: rgba(251, 191, 36, 0.22);
            transform: scale(1.03);
        }

        .overall-badge .num {
            font-size: 1.15rem;
            font-weight: 800;
            color: var(--accent-gold);
            line-height: 1.1;
        }

        .overall-badge .label {
            font-size: 0.65rem;
            color: #d97706;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.05em;
        }

        .col-content {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            flex: 1;
        }

        /* Subcards */
        .text-link {
            color: var(--accent);
            text-decoration: underline;
            word-break: break-all;
            font-weight: 500;
            transition: color 0.2s;
        }

        .text-link:hover {
            color: #ffffff;
            text-decoration: underline;
        }

        .subcard {
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .subcard-title {
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--accent);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Horarios */
        .schedule-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(30, 41, 59, 0.5);
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        .schedule-row:hover {
            background: rgba(30, 41, 59, 0.8);
            border-color: var(--border-hover);
        }

        .schedule-label {
            color: var(--text-secondary);
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .schedule-time {
            font-weight: 700;
            color: var(--text-primary);
        }

        .schedule-badge {
            font-size: 0.7rem;
            padding: 2px 8px;
            border-radius: 6px;
            font-weight: 600;
        }

        .badge-active {
            background: rgba(16, 185, 129, 0.2);
            color: var(--accent-green);
        }

        .badge-finished {
            background: rgba(148, 163, 184, 0.15);
            color: var(--text-secondary);
        }

        .badge-none {
            background: rgba(239, 68, 68, 0.12);
            color: var(--accent-red);
        }

        .lessons-accordion {
            background: rgba(11, 17, 32, 0.6);
            border: 1px dashed rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 8px 10px;
            display: none;
            flex-direction: column;
            gap: 6px;
            font-size: 0.78rem;
        }

        .lesson-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            padding-bottom: 4px;
        }

        .lesson-item.event {
            background: rgba(14, 165, 233, 0.12);
            border: 1px solid rgba(14, 165, 233, 0.25);
            border-radius: 6px;
            padding: 5px 8px;
            margin: 2px 0;
        }

        .lesson-item.event .lesson-time {
            color: #38bdf8;
            font-weight: 700;
        }

        .lesson-item.event .lesson-name {
            color: #e0f2fe;
            font-weight: 700;
        }

        .lesson-item.canceled {
            opacity: 0.6;
        }

        .lesson-item.canceled .lesson-name {
            text-decoration: line-through;
            color: var(--text-muted);
        }

        .lesson-canceled-badge {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            font-size: 0.68rem;
            padding: 1px 5px;
            border-radius: 4px;
            font-weight: 600;
            text-decoration: none;
            display: inline-block;
            margin-left: 4px;
        }

        .lesson-time {
            color: var(--accent);
            font-weight: 600;
            font-family: monospace;
        }

        .lesson-name {
            font-weight: 600;
            color: var(--text-primary);
        }

        .lesson-extra {
            color: var(--text-muted);
            font-size: 0.72rem;
        }

        /* Exámenes y Deberes Items */
        .item-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .item-card {
            background: rgba(30, 41, 59, 0.45);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 9px 11px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 0.82rem;
            transition: all 0.15s;
            cursor: pointer;
        }

        .item-card:hover {
            background: rgba(30, 41, 59, 0.75);
            border-color: var(--border-hover);
        }

        .item-card.done {
            opacity: 0.5;
            text-decoration: line-through;
        }

        .item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .item-date {
            font-size: 0.75rem;
            color: var(--accent-gold);
            font-weight: 600;
        }

        .item-subject {
            font-weight: 700;
            color: var(--text-primary);
        }

        .item-topic {
            color: var(--text-secondary);
            font-size: 0.8rem;
            line-height: 1.35;
        }

        .item-actions {
            display: flex;
            justify-content: flex-end;
            margin-top: 4px;
        }

        .btn-check-task {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: var(--text-secondary);
            font-size: 0.72rem;
            padding: 3px 10px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-check-task:hover {
            border-color: var(--accent-green);
            color: var(--accent-green);
            background: rgba(16, 185, 129, 0.1);
        }

        /* Notas Pills */
        .grades-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }

        .grade-pill {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 0.78rem;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .grade-pill:hover {
            border-color: var(--accent);
            background: rgba(56, 189, 248, 0.12);
        }

        .grade-pill.recent {
            border-color: var(--accent-gold);
            background: rgba(251, 191, 36, 0.12);
        }

        .grade-val {
            font-weight: 800;
            color: var(--accent-gold);
        }

        .grade-subj {
            color: var(--text-secondary);
            font-size: 0.72rem;
        }

        /* Mensajes */
        .msg-card {
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 9px 11px;
            font-size: 0.8rem;
            display: flex;
            flex-direction: column;
            gap: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .msg-card:hover {
            background: rgba(30, 41, 59, 0.75);
            border-color: var(--border-hover);
        }

        .msg-sender {
            font-weight: 700;
            color: var(--accent-purple);
            font-size: 0.75rem;
        }

        .msg-topic {
            font-weight: 600;
            color: var(--text-primary);
        }

        .msg-text {
            color: var(--text-secondary);
            font-size: 0.76rem;
            line-height: 1.35;
        }

        .empty-state {
            color: var(--text-muted);
            font-size: 0.78rem;
            font-style: italic;
            padding: 6px 0;
            text-align: center;
        }

        /* Modal General */
        .modal-backdrop {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(8px);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            padding: 16px;
        }

        .modal-content {
            background: #111827;
            border: 1px solid var(--border-color);
            border-radius: var(--card-radius);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
            width: 100%;
            max-width: 650px;
            max-height: 90vh;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 18px;
            padding: 24px;
            animation: modalFadeIn 0.2s ease-out;
        }

        @keyframes modalFadeIn {
            from { opacity: 0; transform: scale(0.96); }
            to { opacity: 1; transform: scale(1); }
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 14px;
        }

        .modal-header h2 {
            font-size: 1.15rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn-close {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 1.4rem;
            cursor: pointer;
            line-height: 1;
            padding: 4px;
        }

        .btn-close:hover {
            color: var(--text-primary);
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        label {
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .input-row {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        select, input[type="number"] {
            background: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            padding: 9px 12px;
            font-size: 0.9rem;
            outline: none;
            flex: 1;
        }

        .actions-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
        }

        @media (max-width: 550px) {
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        .stat-box {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }

        .stat-value {
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--accent);
        }

        .stat-label {
            font-size: 0.7rem;
            color: var(--text-secondary);
            margin-top: 3px;
        }

        .logs-box {
            background: #090d16;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px;
            font-family: monospace;
            font-size: 0.76rem;
            max-height: 140px;
            overflow-y: auto;
            color: #cbd5e1;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        /* Tabla de Notas Completa */
        .grades-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }

        .grades-table th {
            text-align: left;
            padding: 8px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-weight: 600;
        }

        .grades-table td {
            padding: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }

        /* Toast */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #1e293b;
            color: white;
            padding: 12px 20px;
            border-radius: 10px;
            border-left: 4px solid var(--accent);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            display: none;
            z-index: 2000;
            animation: fadeIn 0.3s;
            font-size: 0.88rem;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header Principal -->
        <header>
            <div class="brand">
                <div class="avatar-wrap">
                    <img src="avatar.jpg" alt="Srta. Rottenmeier">
                </div>
                <div class="brand-title">
                    <h1>Srta. Rottenmeier</h1>
                    <p>Monitor Escolar de Librus & Asistente Familiar (<a href="https://t.me/srta_rottenmeier_bot" target="_blank" rel="noopener noreferrer">@srta_rottenmeier_bot ↗</a>)</p>
                </div>
            </div>
            <div class="header-actions">
                <div class="badge-status">
                    <div class="status-dot"></div>
                    <span id="botStatusText">En línea</span>
                </div>
                <button class="btn btn-secondary" onclick="refreshDashboard()" id="btnRefresh">
                    🔄 Sincronizar Librus
                </button>
                <button class="btn" onclick="openConfigModal()">
                    ⚙️ Configuración
                </button>
            </div>
        </header>

        <!-- Barra informativa -->
        <div class="info-bar">
            <span>Última sincronización con Librus: <b id="lastSyncText" style="color:var(--text-primary)">Cargando...</b></span>
            <span>Servidor: <b>alpejska</b> • <a href="https://synergia.librus.pl/" target="_blank" rel="noopener noreferrer">Portal Librus Synergia ↗</a></span>
        </div>

        <!-- 3 Columnas de los Hijos -->
        <div class="pupils-grid" id="pupilsGrid">
            <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-secondary);">
                ⏳ Conectando con Librus Synergia para consultar horarios, notas y tareas...
            </div>
        </div>
    </div>

    <!-- Modal de Configuración y Herramientas -->
    <div class="modal-backdrop" id="configModal" onclick="closeModalOnBackdrop(event, 'configModal')">
        <div class="modal-content">
            <div class="modal-header">
                <h2>⚙️ Configuración & Herramientas</h2>
                <button class="btn-close" onclick="closeModal('configModal')">✕</button>
            </div>

            <!-- Frecuencia de Comprobación -->
            <div class="form-group">
                <label>Frecuencia de comprobación automática de Librus:</label>
                <div class="input-row">
                    <select id="intervalSelect" onchange="handleSelectChange(this.value)">
                        <option value="5">Cada 5 minutos</option>
                        <option value="10">Cada 10 minutos</option>
                        <option value="15" selected>Cada 15 minutos (Recomendado)</option>
                        <option value="30">Cada 30 minutos</option>
                        <option value="45">Cada 45 minutos</option>
                        <option value="60">Cada 60 minutos (1 hora)</option>
                        <option value="custom">Personalizado...</option>
                    </select>
                    <button class="btn" onclick="saveInterval()">💾 Guardar</button>
                </div>
                <div class="input-row" id="customRow" style="display:none; margin-top:4px;">
                    <input type="number" id="customMinutes" min="1" max="1440" placeholder="Minutos..." value="15">
                    <span style="font-size:0.85rem; color:var(--text-secondary);">min</span>
                </div>
            </div>

            <!-- Acciones Rápidas -->
            <div class="form-group">
                <label>Acciones del Daemon:</label>
                <div class="actions-grid">
                    <button class="btn btn-secondary" onclick="triggerAction('check-now', 'Comprobando novedades en Librus...')">
                        🔄 Comprobar Ahora
                    </button>
                    <button class="btn btn-secondary" onclick="triggerAction('send-summary', 'Enviando resumen semanal al Telegram...')">
                        📊 Enviar Resumen al Chat
                    </button>
                    <button class="btn btn-secondary" onclick="triggerAction('prune-now', 'Purgando mensajes > 45h...')">
                        🧹 Purgar Mensajes >45h
                    </button>
                </div>
            </div>

            <!-- Métricas de la BD -->
            <div class="form-group">
                <label>Métricas del Sistema:</label>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-value" id="statNotifications">0</div>
                        <div class="stat-label">Alertas BD</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="statMessagesCache">0</div>
                        <div class="stat-label">Mensajes Caché</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="statChatMessages">0</div>
                        <div class="stat-label">Chat (45h)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="statCompletedTasks">0</div>
                        <div class="stat-label">Tareas Hechas</div>
                    </div>
                </div>
            </div>

            <!-- Consola de Logs -->
            <div class="form-group">
                <label>Registro de Actividad:</label>
                <div class="logs-box" id="logsBox">
                    <div style="color:var(--text-muted)">Cargando logs del daemon...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal Detalle de Calificaciones -->
    <div class="modal-backdrop" id="gradesModal" onclick="closeModalOnBackdrop(event, 'gradesModal')">
        <div class="modal-content" style="max-width: 750px;">
            <div class="modal-header">
                <h2 id="gradesModalTitle">📊 Desglose de Calificaciones</h2>
                <button class="btn-close" onclick="closeModal('gradesModal')">✕</button>
            </div>
            <div id="gradesModalContent">
                <!-- Se llena dinámicamente -->
            </div>
        </div>
    </div>

    <!-- Modal Detalle de Examen -->
    <div class="modal-backdrop" id="examModal" onclick="closeModalOnBackdrop(event, 'examModal')">
        <div class="modal-content" style="max-width: 650px;">
            <div class="modal-header">
                <h2 id="examModalTitle">🎯 Detalle del Examen</h2>
                <button class="btn-close" onclick="closeModal('examModal')">✕</button>
            </div>
            <div id="examModalContent" style="display:flex; flex-direction:column; gap:12px; font-size:0.9rem; line-height:1.5;"></div>
        </div>
    </div>

    <!-- Modal Detalle de Tarea -->
    <div class="modal-backdrop" id="hwModal" onclick="closeModalOnBackdrop(event, 'hwModal')">
        <div class="modal-content" style="max-width: 650px;">
            <div class="modal-header">
                <h2 id="hwModalTitle">📝 Detalle de la Tarea</h2>
                <button class="btn-close" onclick="closeModal('hwModal')">✕</button>
            </div>
            <div id="hwModalContent" style="display:flex; flex-direction:column; gap:12px; font-size:0.9rem; line-height:1.5;"></div>
        </div>
    </div>

    <!-- Modal Detalle de Mensaje -->
    <div class="modal-backdrop" id="msgModal" onclick="closeModalOnBackdrop(event, 'msgModal')">
        <div class="modal-content" style="max-width: 650px;">
            <div class="modal-header">
                <h2 id="msgModalTitle">✉️ Mensaje del Profesor</h2>
                <button class="btn-close" onclick="closeModal('msgModal')">✕</button>
            </div>
            <div id="msgModalContent" style="display:flex; flex-direction:column; gap:12px; font-size:0.9rem; line-height:1.5;">
                <!-- Se llena dinámicamente -->
            </div>
        </div>
    </div>

    <div class="toast" id="toast">Acción completada</div>

    <script>
        // Definición de base URL segura para endpoints API
        const BASE_URL = window.location.pathname.endsWith('/') ? window.location.pathname : window.location.pathname + '/';

        let currentPupilsData = [];

        function showToast(msg, isError = false) {
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.style.borderLeftColor = isError ? 'var(--accent-red)' : 'var(--accent)';
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3500);
        }

        function openConfigModal() {
            document.getElementById('configModal').style.display = 'flex';
            loadSettingsAndStats();
        }

        function closeModal(id) {
            document.getElementById(id).style.display = 'none';
        }

        function closeModalOnBackdrop(e, id) {
            if (e.target.id === id) closeModal(id);
        }

        function handleSelectChange(val) {
            document.getElementById('customRow').style.display = (val === 'custom') ? 'flex' : 'none';
        }

        const DIAS_SEMANA_COMPLETO = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

        function formatFriendlyDate(dateStr) {
            if (!dateStr) return '';
            try {
                const parts = dateStr.slice(0, 10).split('-');
                if (parts.length === 3) {
                    const y = parseInt(parts[0], 10);
                    const m = parseInt(parts[1], 10) - 1;
                    const d = parseInt(parts[2], 10);
                    const dateObj = new Date(y, m, d);
                    const dayIdx = (dateObj.getDay() + 6) % 7;
                    const dayName = DIAS_SEMANA_COMPLETO[dayIdx];
                    const dd = String(d).padStart(2, '0');
                    const mm = String(m + 1).padStart(2, '0');
                    return `${dayName} ${dd}/${mm}`;
                }
            } catch(e) {}
            return dateStr;
        }

        function autolink(text) {
            if (!text) return '';
            const escaped = text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");

            const urlPattern = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi;
            return escaped.replace(urlPattern, function(matched) {
                let clean = matched;
                let suffix = '';
                const punctMatch = clean.match(/[.,;:!?)]+$/);
                if (punctMatch) {
                    suffix = punctMatch[0];
                    clean = clean.slice(0, -suffix.length);
                }
                const fullHref = clean.startsWith('www.') ? 'https://' + clean : clean;
                return `<a href="${fullHref}" target="_blank" rel="noopener noreferrer" class="text-link" onclick="event.stopPropagation();">${clean}</a>${suffix}`;
            });
        }

        function openExamModal(username, examId) {
            const pupil = currentPupilsData.find(p => p.username === username);
            if (!pupil) return;
            const exam = (pupil.exams || []).find(e => String(e.id) === String(examId));
            if (!exam) return;

            const friendlyDate = exam.date_formatted || formatFriendlyDate(exam.date);
            document.getElementById('examModalTitle').innerText = `${exam.category_icon || '🎯'} ${exam.category}: ${exam.subject}`;
            document.getElementById('examModalContent').innerHTML = `
                <div style="background:rgba(30,41,59,0.5); padding:10px 14px; border-radius:8px; border:1px solid var(--border-color); display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">
                    <div>📅 <b>Fecha:</b> <span style="color:var(--accent-gold); font-weight:700;">${friendlyDate}</span> ${exam.time ? `(${exam.time})` : ''}</div>
                    <div>🎒 <b>Alumno:</b> ${pupil.name}</div>
                </div>
                <div style="background:rgba(15,23,42,0.6); padding:14px; border-radius:8px; border:1px solid var(--border-color); color:#cbd5e1; white-space:pre-wrap;">${autolink(exam.content || 'Sin temario o instrucciones adicionales')}</div>
                ${exam.content_raw && exam.content_raw !== exam.content ? `
                    <details style="font-size:0.8rem; color:var(--text-muted); cursor:pointer;">
                        <summary>🇵🇱 Ver texto original en polaco</summary>
                        <div style="margin-top:6px; background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; white-space:pre-wrap;">${autolink(exam.content_raw)}</div>
                    </details>
                ` : ''}
            `;
            document.getElementById('examModal').style.display = 'flex';
        }

        function openHwModal(username, hwId) {
            const pupil = currentPupilsData.find(p => p.username === username);
            if (!pupil) return;
            const hw = (pupil.homework || []).find(h => String(h.id) === String(hwId));
            if (!hw) return;

            const friendlyDueDate = hw.due_date_formatted || formatFriendlyDate(hw.due_date);
            document.getElementById('hwModalTitle').innerText = `📝 Tarea: ${hw.subject}`;
            document.getElementById('hwModalContent').innerHTML = `
                <div style="background:rgba(30,41,59,0.5); padding:10px 14px; border-radius:8px; border:1px solid var(--border-color); display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">
                    <div>⏰ <b>Fecha de Entrega:</b> <span style="color:var(--accent-gold); font-weight:700;">${friendlyDueDate}</span></div>
                    <div>🎒 <b>Alumno:</b> ${pupil.name}</div>
                </div>
                <div style="font-weight:700; color:var(--text-primary); font-size:1rem;">${autolink(hw.topic)}</div>
                <div style="background:rgba(15,23,42,0.6); padding:14px; border-radius:8px; border:1px solid var(--border-color); color:#cbd5e1; white-space:pre-wrap;">${autolink(hw.content || 'Sin instrucciones adicionales')}</div>
                <div style="display:flex; justify-content:flex-end;">
                    <button class="btn btn-secondary" onclick="toggleTask('${pupil.username}', '${hw.id}'); closeModal('hwModal');">
                        ${hw.is_done ? '✔ Marcada como hecha (pulsa para desmarcar)' : '✅ Marcar como hecha'}
                    </button>
                </div>
            `;
            document.getElementById('hwModal').style.display = 'flex';
        }

        // Desplegar u ocultar clases de un día
        function toggleLessons(username, dateIso) {
            const el = document.getElementById(`lessons-${username}-${dateIso}`);
            if (el) {
                el.style.display = (el.style.display === 'flex') ? 'none' : 'flex';
            }
        }

        // Abrir modal con todas las notas
        function openGradesModal(username) {
            const pupil = currentPupilsData.find(p => p.username === username);
            if (!pupil) return;

            document.getElementById('gradesModalTitle').innerText = `📊 Calificaciones de ${pupil.name}`;
            const subjs = pupil.subject_averages || [];
            
            let html = `
                <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(251, 191, 36, 0.12); padding:12px 16px; border-radius:10px; border:1px solid rgba(251, 191, 36, 0.3); margin-bottom:12px;">
                    <span style="font-weight:600; color:var(--text-primary)">Promedio General Ponderado:</span>
                    <span style="font-size:1.3rem; font-weight:800; color:var(--accent-gold);">${pupil.overall_average || '-'}</span>
                </div>
                <table class="grades-table">
                    <thead>
                        <tr>
                            <th>Asignatura</th>
                            <th>Notas</th>
                            <th style="text-align:right;">Promedio</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            if (!subjs.length) {
                html += `<tr><td colspan="3" style="text-align:center; padding:16px; color:var(--text-muted);">Sin calificaciones registradas este curso.</td></tr>`;
            } else {
                html += subjs.map(s => `
                    <tr>
                        <td style="font-weight:600; color:var(--text-primary);">${s.subject}</td>
                        <td>${(s.grades || []).map(g => `<span style="background:rgba(255,255,255,0.08); padding:2px 6px; border-radius:4px; margin-right:4px; font-weight:700;">${g}</span>`).join('')}</td>
                        <td style="text-align:right; font-weight:800; color:${s.average >= 4.5 ? 'var(--accent-green)' : (s.average >= 3.0 ? 'var(--accent-gold)' : 'var(--accent-red)')};">${s.average}</td>
                    </tr>
                `).join('');
            }

            html += `</tbody></table>`;
            document.getElementById('gradesModalContent').innerHTML = html;
            document.getElementById('gradesModal').style.display = 'flex';
        }

        // Abrir modal de mensaje completo
        function openMsgModal(username, msgId) {
            const pupil = currentPupilsData.find(p => p.username === username);
            if (!pupil) return;
            const msg = (pupil.recent_messages || []).find(m => String(m.id) === String(msgId));
            if (!msg) return;

            document.getElementById('msgModalTitle').innerText = `✉️ Mensaje de ${msg.sender}`;
            document.getElementById('msgModalContent').innerHTML = `
                <div style="background:rgba(30,41,59,0.5); padding:10px 14px; border-radius:8px; border:1px solid var(--border-color);">
                    <div style="color:var(--accent-purple); font-weight:700;">${msg.sender}</div>
                    <div style="font-size:0.8rem; color:var(--text-muted);">${msg.date}</div>
                    <div style="font-weight:700; color:var(--text-primary); margin-top:4px;">Asunto: ${msg.topic}</div>
                </div>
                <div style="background:rgba(15,23,42,0.6); padding:14px; border-radius:8px; border:1px solid var(--border-color); color:#cbd5e1; white-space:pre-wrap;">${autolink(msg.body)}</div>
            `;
            document.getElementById('msgModal').style.display = 'flex';
        }

        async function loadOverview() {
            try {
                const res = await fetch(BASE_URL + 'api/overview');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                renderOverview(data);
            } catch (e) {
                console.error("Error al cargar overview:", e);
            }
        }

        async function refreshDashboard() {
            const btn = document.getElementById('btnRefresh');
            btn.innerText = '⏳ Sincronizando...';
            btn.disabled = true;
            try {
                const res = await fetch(BASE_URL + 'api/overview/refresh', { method: 'POST' });
                const data = await res.json();
                renderOverview(data);
                showToast("✅ Datos sincronizados con Librus");
            } catch (e) {
                showToast("Error al sincronizar con Librus", true);
            } finally {
                btn.innerText = '🔄 Sincronizar Librus';
                btn.disabled = false;
            }
        }

        function renderOverview(data) {
            document.getElementById('lastSyncText').innerText = data.last_sync || 'Recién sincronizado';
            const pupils = (data.pupils || []).slice();
            pupils.sort((a, b) => {
                const idA = parseInt(String(a.username || a.librus_username || '').replace(/\D/g, '') || '0', 10);
                const idB = parseInt(String(b.username || b.librus_username || '').replace(/\D/g, '') || '0', 10);
                return idA - idB;
            });
            currentPupilsData = pupils;

            if (!pupils.length) {
                document.getElementById('pupilsGrid').innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:30px;">No hay datos disponibles aún. Pulsa Sincronizar Librus.</div>';
                return;
            }

            const html = pupils.map(p => {
                // Horarios con acordeón interactivo de clases
                const schedulesHtml = (p.schedules || []).map(s => {
                    let badge = '';
                    if (!s.entry || !s.exit) {
                        badge = '<span class="schedule-badge badge-none">Sin clases</span>';
                    } else {
                        badge = `<span class="schedule-badge badge-active">${s.entry} → ${s.exit}</span>`;
                    }

                    const lessonsList = (s.lessons || []).map(l => {
                        if (l.is_event) {
                            const tooltip = (l.details || l.subject || '').replace(/"/g, '&quot;');
                            return `
                                <div class="lesson-item event" title="${tooltip}">
                                    <span class="lesson-time">${l.hour_from}-${l.hour_to}</span>
                                    <span class="lesson-name">${l.subject}</span>
                                    <span class="lesson-extra">${l.extra || 'Evento'}</span>
                                </div>
                            `;
                        }
                        if (l.is_canceled) {
                            return `
                                <div class="lesson-item canceled" title="Clase cancelada">
                                    <span class="lesson-time">${l.hour_from}-${l.hour_to}</span>
                                    <span class="lesson-name">${l.subject} <span class="lesson-canceled-badge">Cancelada</span></span>
                                    <span class="lesson-extra">${l.classroom ? 'Aula ' + l.classroom : ''}</span>
                                </div>
                            `;
                        }
                        return `
                            <div class="lesson-item">
                                <span class="lesson-time">${l.hour_from}-${l.hour_to}</span>
                                <span class="lesson-name">${l.subject}</span>
                                <span class="lesson-extra">${l.classroom ? 'Aula ' + l.classroom : ''}</span>
                            </div>
                        `;
                    }).join('') || '<div style="color:var(--text-muted); font-style:italic;">No hay clases programadas para este día</div>';

                    return `
                        <div>
                            <div class="schedule-row" onclick="toggleLessons('${p.username}', '${s.date_iso}')" title="Pulsa para ver las asignaturas y aulas">
                                <span class="schedule-label">
                                    <span>${s.label} (${s.day_name}):</span>
                                </span>
                                ${badge}
                            </div>
                            <div class="lessons-accordion" id="lessons-${p.username}-${s.date_iso}">
                                <div style="font-weight:700; color:var(--text-secondary); margin-bottom:2px;">📚 Clases (${s.day_name} ${s.date}):</div>
                                ${lessonsList}
                            </div>
                        </div>
                    `;
                }).join('') || '<div class="empty-state">Sin horario disponible</div>';

                // Exámenes
                const examsHtml = (p.exams || []).slice(0, 6).map(e => {
                    const friendlyDate = e.date_formatted || formatFriendlyDate(e.date);
                    return `
                    <div class="item-card" onclick="openExamModal('${p.username}', '${e.id}')" title="Pulsa para ver los detalles del examen">
                        <div class="item-header">
                            <span class="item-subject">${e.category_icon || '🎯'} ${e.subject}</span>
                            <span class="item-date">${friendlyDate}</span>
                        </div>
                        <div class="item-topic"><b>${e.category}:</b> ${autolink(e.content || 'Sin temario especificado')}</div>
                    </div>
                    `;
                }).join('') || '<div class="empty-state">✨ Sin exámenes programados en 14 días</div>';

                // Tareas
                const hwHtml = (p.homework || []).slice(0, 6).map(h => {
                    const friendlyDueDate = h.due_date_formatted || formatFriendlyDate(h.due_date);
                    return `
                    <div class="item-card ${h.is_done ? 'done' : ''}" id="task-${h.id}" onclick="openHwModal('${p.username}', '${h.id}')" title="Pulsa para ver las instrucciones completas">
                        <div class="item-header">
                            <span class="item-subject">📝 ${h.subject}</span>
                            <span class="item-date">${friendlyDueDate}</span>
                        </div>
                        <div class="item-topic">${autolink(h.topic || h.content)}</div>
                        <div class="item-actions" onclick="event.stopPropagation();">
                            <button class="btn-check-task" onclick="toggleTask('${p.username}', '${h.id}')">
                                ${h.is_done ? '✔ Hecha' : '⚪ Marcar hecha'}
                            </button>
                        </div>
                    </div>
                    `;
                }).join('') || '<div class="empty-state">✨ Todo al día, sin tareas pendientes</div>';

                // Notas Recientes
                const recentGradesHtml = (p.recent_grades || []).slice(0, 8).map(g => `
                    <div class="grade-pill recent" title="${g.category} (${g.date}) - Ponderación: ${g.weight}">
                        <span class="grade-val">${g.grade}</span>
                        <span class="grade-subj">${g.subject}</span>
                    </div>
                `).join('');

                // Asignaturas y Promedios
                const subjAvgHtml = (p.subject_averages || []).slice(0, 6).map(sa => `
                    <div class="grade-pill" title="Notas: ${sa.grades.join(', ')}">
                        <span class="grade-subj">${sa.subject}:</span>
                        <span class="grade-val" style="color:var(--text-primary)">${sa.average}</span>
                    </div>
                `).join('');

                // Mensajes de Profesores
                const msgsHtml = (p.recent_messages || []).slice(0, 3).map(m => `
                    <div class="msg-card" onclick="openMsgModal('${p.username}', '${m.id}')" title="Pulsa para leer el mensaje completo">
                        <div class="msg-sender">✉️ ${m.sender} • <span style="color:var(--text-muted)">${m.date.slice(5, 16)}</span></div>
                        <div class="msg-topic">${m.topic}</div>
                        <div class="msg-text">${autolink(m.body.length > 120 ? m.body.slice(0, 120) + '...' : m.body)}</div>
                    </div>
                `).join('') || '<div class="empty-state">Sin mensajes recientes</div>';

                return `
                    <div class="pupil-col">
                        <div class="col-header">
                            <div class="col-title">
                                <span class="col-icon">${p.icon || '👤'}</span>
                                <div>
                                    <div class="col-name">${p.name || p.username}</div>
                                    <div class="col-user">
                                        <a href="https://synergia.librus.pl/" target="_blank" rel="noopener noreferrer" title="Abrir portal oficial de Librus">
                                            Librus: <code>${p.username}</code> ↗
                                        </a>
                                    </div>
                                </div>
                            </div>
                            <div class="overall-badge" onclick="openGradesModal('${p.username}')" title="Ver desglose completo de notas">
                                <span class="num">${p.overall_average || '-'}</span>
                                <span class="label">Promedio ↗</span>
                            </div>
                        </div>

                        <div class="col-content">
                            <!-- Horario -->
                            <div class="subcard">
                                <div class="subcard-title">
                                    <span>🕒 Horario de Clases</span>
                                    <span style="font-size:0.7rem; color:var(--text-muted); font-weight:normal;">Pulsa día para ver aulas</span>
                                </div>
                                ${schedulesHtml}
                            </div>

                            <!-- Exámenes -->
                            <div class="subcard">
                                <div class="subcard-title">
                                    <span>🎯 Próximos Exámenes</span>
                                    <span style="font-size:0.75rem; color:var(--text-muted);">${(p.exams || []).length}</span>
                                </div>
                                <div class="item-list">${examsHtml}</div>
                            </div>

                            <!-- Deberes -->
                            <div class="subcard">
                                <div class="subcard-title">
                                    <span>📝 Tareas & Entregas</span>
                                    <span style="font-size:0.75rem; color:var(--text-muted);">${(p.homework || []).length}</span>
                                </div>
                                <div class="item-list">${hwHtml}</div>
                            </div>

                            <!-- Calificaciones -->
                            <div class="subcard">
                                <div class="subcard-title">
                                    <span>⭐ Calificaciones</span>
                                    <button class="btn btn-secondary" style="padding:2px 8px; font-size:0.7rem;" onclick="openGradesModal('${p.username}')">Ver todas ↗</button>
                                </div>
                                ${recentGradesHtml ? `
                                    <div style="font-size:0.75rem; color:var(--accent-gold); font-weight:600; margin-bottom:2px;">Últimas notas (7 días):</div>
                                    <div class="grades-wrap" style="margin-bottom:8px;">${recentGradesHtml}</div>
                                ` : ''}
                                <div style="font-size:0.75rem; color:var(--text-secondary); margin-bottom:2px;">Promedios por asignatura:</div>
                                <div class="grades-wrap">${subjAvgHtml || '<div class="empty-state">Sin notas aún</div>'}</div>
                            </div>

                            <!-- Mensajes -->
                            <div class="subcard">
                                <div class="subcard-title">
                                    <span>✉️ Comunicados</span>
                                    <span style="font-size:0.7rem; color:var(--text-muted); font-weight:normal;">Pulsa para leer</span>
                                </div>
                                <div class="item-list">${msgsHtml}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            document.getElementById('pupilsGrid').innerHTML = html;
        }

        async function toggleTask(username, taskId) {
            try {
                const res = await fetch(BASE_URL + 'api/task-toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, task_id: taskId })
                });
                const data = await res.json();
                if (data.ok) {
                    showToast(data.is_done ? "Tarea marcada como hecha" : "Tarea desmarcada");
                    loadOverview();
                }
            } catch (e) {
                showToast("Error al actualizar tarea", true);
            }
        }

        async function loadSettingsAndStats() {
            try {
                const res = await fetch(BASE_URL + 'api/status');
                const data = await res.json();

                const mins = data.check_interval_minutes || 15;
                const sel = document.getElementById('intervalSelect');
                if (['5','10','15','30','45','60'].includes(String(mins))) {
                    sel.value = String(mins);
                    document.getElementById('customRow').style.display = 'none';
                } else {
                    sel.value = 'custom';
                    document.getElementById('customRow').style.display = 'flex';
                    document.getElementById('customMinutes').value = mins;
                }

                if (data.stats) {
                    document.getElementById('statNotifications').innerText = data.stats.notifications || 0;
                    document.getElementById('statMessagesCache').innerText = data.stats.messages_cache || 0;
                    document.getElementById('statChatMessages').innerText = data.stats.chat_messages || 0;
                    document.getElementById('statCompletedTasks').innerText = data.stats.completed_tasks || 0;
                }

                if (data.logs && data.logs.length > 0) {
                    const logsBox = document.getElementById('logsBox');
                    logsBox.innerHTML = data.logs.map(l => `
                        <div><span style="color:var(--text-muted)">[${l.time}]</span> ${l.message}</div>
                    `).join('');
                }
            } catch (e) {
                console.error("Error al cargar settings:", e);
            }
        }

        async function saveInterval() {
            let mins = document.getElementById('intervalSelect').value;
            if (mins === 'custom') {
                mins = document.getElementById('customMinutes').value;
            }
            mins = parseInt(mins, 10);
            if (!mins || mins < 1) {
                showToast("Introduce un intervalo válido", true);
                return;
            }

            try {
                const res = await fetch(BASE_URL + 'api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ check_interval_minutes: mins })
                });
                const data = await res.json();
                if (data.ok) {
                    showToast(`✅ Frecuencia guardada: cada ${mins} min`);
                    loadSettingsAndStats();
                }
            } catch (e) {
                showToast("Error de conexión", true);
            }
        }

        async function triggerAction(endpoint, msg) {
            showToast(msg);
            try {
                const res = await fetch(BASE_URL + `api/${endpoint}`, { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    showToast(data.message || "Acción realizada");
                    loadSettingsAndStats();
                } else {
                    showToast(data.error || "Error", true);
                }
            } catch (e) {
                showToast("Error al ejecutar", true);
            }
        }

        // Carga inicial
        loadOverview();
        // Refresco de fondo cada 20 segundos
        setInterval(loadOverview, 20000);
    </script>
</body>
</html>
"""


class WebPanel:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/avatar.jpg", self.handle_avatar)
        self.app.router.add_get("/api/overview", self.handle_overview)
        self.app.router.add_post("/api/overview/refresh", self.handle_overview_refresh)
        self.app.router.add_post("/api/task-toggle", self.handle_task_toggle)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_post("/api/settings", self.handle_settings)
        self.app.router.add_post("/api/check-now", self.handle_check_now)
        self.app.router.add_post("/api/send-summary", self.handle_send_summary)
        self.app.router.add_post("/api/prune-now", self.handle_prune_now)

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=HTML_TEMPLATE, content_type="text/html", charset="utf-8")

    async def handle_avatar(self, request: web.Request) -> web.Response:
        paths = ["/home/jose/librus/avatar.jpg", "avatar.jpg", "z:/Jose/Desarrollos/HomeAssistant/avatar.jpg"]
        for p in paths:
            if os.path.exists(p):
                return web.FileResponse(p)
        return web.Response(status=404)

    async def handle_overview(self, request: web.Request) -> web.Response:
        cached = getattr(self.bot, "cached_overview", [])
        last_sync = getattr(self.bot, "last_overview_time", "Nunca")
        if not cached:
            asyncio.create_task(self.bot.refresh_dashboard_overview())
        return web.json_response({
            "ok": True,
            "last_sync": last_sync,
            "pupils": cached
        })

    async def handle_overview_refresh(self, request: web.Request) -> web.Response:
        new_data = await self.bot.refresh_dashboard_overview()
        return web.json_response({
            "ok": True,
            "last_sync": getattr(self.bot, "last_overview_time", "Ahora mismo"),
            "pupils": new_data
        })

    async def handle_task_toggle(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            u = data.get("username")
            task_id = str(data.get("task_id"))
            admin_cid = db.get_admin_chat_id()
            is_done = db.is_task_completed(admin_cid, u, task_id)
            if is_done:
                db.unmark_task_completed(admin_cid, u, task_id)
                new_state = False
            else:
                db.mark_task_completed(admin_cid, u, task_id)
                new_state = True

            for p in getattr(self.bot, "cached_overview", []):
                if p.get("username") == u:
                    for h in p.get("homework", []):
                        if str(h.get("id")) == task_id:
                            h["is_done"] = new_state

            return web.json_response({"ok": True, "is_done": new_state})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    async def handle_status(self, request: web.Request) -> web.Response:
        interval = int(db.get_setting("check_interval_minutes", "15"))
        pupils = db.get_all_active_pupils()
        safe_pupils = [
            {"librus_username": p["librus_username"], "name": p.get("name", ""), "icon": p.get("icon", "👤")}
            for p in pupils
        ]
        stats = db.get_system_stats()
        status_data = {
            "ok": True,
            "running": True,
            "check_interval_minutes": interval,
            "last_check": getattr(self.bot, "last_check_time", "Nunca"),
            "pupils": safe_pupils,
            "stats": stats,
            "logs": getattr(self.bot, "event_logs", [])[-25:],
        }
        return web.json_response(status_data)

    async def handle_settings(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            mins = int(data.get("check_interval_minutes", 15))
            if mins < 1:
                return web.json_response({"ok": False, "error": "Intervalo debe ser >= 1 min"})
            db.set_setting("check_interval_minutes", str(mins))
            if hasattr(self.bot, "update_interval"):
                self.bot.update_interval(mins)
            self.bot.log_event(f"Intervalo de comprobación actualizado a {mins} minutos")
            return web.json_response({"ok": True, "check_interval_minutes": mins})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    async def handle_check_now(self, request: web.Request) -> web.Response:
        try:
            self.bot.log_event("Comprobación manual iniciada desde el panel web")
            asyncio.create_task(self.bot.trigger_check_now())
            return web.json_response({"ok": True, "message": "Comprobación iniciada en segundo plano"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_send_summary(self, request: web.Request) -> web.Response:
        try:
            self.bot.log_event("Envío de resumen solicitado desde el panel web")
            asyncio.create_task(self.bot.trigger_summary_now())
            return web.json_response({"ok": True, "message": "Resumen en proceso de envío a Telegram"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_prune_now(self, request: web.Request) -> web.Response:
        try:
            self.bot.log_event("Purga de mensajes (>45h) ejecutada desde panel web")
            asyncio.create_task(self.bot.trigger_prune_now())
            return web.json_response({"ok": True, "message": "Purga de mensajes ejecutada"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
