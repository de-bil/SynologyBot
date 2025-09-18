#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
import logging
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import ssl
import urllib3
from urllib3.exceptions import InsecureRequestWarning
import re
from typing import Dict, List, Optional, Tuple
import datetime
from pathlib import Path
import random
import difflib
import sqlite3
from collections import defaultdict
import importlib

def format_timedelta(delta):
    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours}ч {minutes}м {seconds}с"
    elif minutes > 0:
        return f"{minutes}м {seconds}с"
    else:
        return f"{seconds}с"
     
# Отключаем предупреждения о небезопасных SSL соединениях
urllib3.disable_warnings(InsecureRequestWarning)

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка цветного логирования
class ColorFormatter(logging.Formatter):
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    green = "\x1b[38;5;82m"
    purple = "\x1b[38;5;129m"
    reset = "\x1b[0m"

    def __init__(self, fmt):
        super().__init__(fmt)
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Настройка логирования
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Формат для файла
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Формат для консоли
    console_formatter = ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Файловый обработчик
    file_handler = logging.FileHandler('synology_bot.log', encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    
    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

app = Flask(__name__)

# Глобальная переменная для хранения состояния пользователей
user_sessions = {}

class UserSession:
    """Класс для управления сессиями пользователей"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.state = 'main_menu'  # main_menu, category_selected, question_selected
        self.selected_category = None
        self.selected_question = None
        self.last_interaction = datetime.datetime.now()
    
    def reset(self):
        """Сброс сессии к главному меню"""
        self.state = 'main_menu'
        self.selected_category = None
        self.selected_question = None
        self.last_interaction = datetime.datetime.now()

@app.route('/api/recent-requests', methods=['GET'])
def api_recent_requests():
    """API для получения последних запросов"""
    stats = bot.stats_db.get_statistics()
    return jsonify({
        'recent_requests': [
            {
                'username': req[0],
                'question': req[1],
                'category': req[2] if req[2] else 'N/A',
                'timestamp': req[3]
            }
            for req in stats['recent_requests']
        ]
    })

@app.route('/api/uptime', methods=['GET'])
def api_uptime():
    """API для получения времени работы"""
    return jsonify({'uptime': format_timedelta(datetime.datetime.now() - start_time)})

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """API для получения статистики"""
    stats = bot.stats_db.get_statistics()
    return jsonify({
        'total_requests': stats['total_requests'],
        'unique_users': stats['unique_users'],
        'uptime': format_timedelta(datetime.datetime.now() - start_time)
    })

@app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({
        'status': 'active',
        'bot_name': bot.bot_name,
        'port': bot.port,
        'uptime': format_timedelta(datetime.datetime.now() - start_time)
    })     

class StatisticsDB:
    def __init__(self):
        self.db_path = 'bot_statistics.db'
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица для запросов пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                username TEXT,
                question TEXT,
                category TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для ответов бота
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                response_text TEXT,
                category TEXT,
                has_buttons INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES user_requests (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_request(self, user_id, username, question, category):
        """Логирование запроса пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO user_requests (user_id, username, question, category)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, question, category))
        
        request_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return request_id
    
    def log_response(self, request_id, response_text, category, has_buttons=False):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bot_responses (request_id, response_text, category, has_buttons)
            VALUES (?, ?, ?, ?)
        ''', (request_id, response_text, category, 1 if has_buttons else 0))
        
        conn.commit()
        conn.close()
    
    def get_statistics(self):
        """Получение статистики"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Общее количество запросов
        cursor.execute('SELECT COUNT(*) FROM user_requests')
        total_requests = cursor.fetchone()[0]
        
        # Количество запросов по категориям
        cursor.execute('''
            SELECT category, COUNT(*) 
            FROM user_requests 
            WHERE category IS NOT NULL 
            GROUP BY category 
            ORDER BY COUNT(*) DESC
        ''')
        category_stats = cursor.fetchall()
        
        # Количество уникальных пользователей
        cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_requests')
        unique_users = cursor.fetchone()[0]
        
        # Последние запросы
        cursor.execute('''
            SELECT username, question, category, timestamp 
            FROM user_requests 
            ORDER BY timestamp DESC 
            LIMIT 10
        ''')
        recent_requests = cursor.fetchall()
        
        conn.close()
        
        return {
            'total_requests': total_requests,
            'unique_users': unique_users,
            'category_stats': category_stats,
            'recent_requests': recent_requests
        }

class SynologyChatBot:
    def __init__(self):
        # Чтение настроек из .env файла
        self.incoming_url = os.getenv('SYNOLOGY_INCOMING_URL', 'https://192-168-10-203.spbuor1.direct.quickconnect.to:5001/webapi/entry.cgi?api=SYNO.Chat.External&method=chatbot&version=2&token=i8ppUgMTrUX7s极会TrUX7s3v9MGBt3RhP6Eoef2Mcs43SdTIX0DV0JG88Qpd6SP6B0esmvRBs')
        self.bot_name = os.getenv('BOT_NAME', 'ИнструкторБот')
        self.port = os.getenv('FLASK_PORT', '5000')
        
        # Инициализация базы данных статистики
        self.stats_db = StatisticsDB()
        
        # База знаний с расширенными ключевыми словами
        self.knowledge_base = self._setup_knowledge_base()
        
        logger.info(f"🎯 Бот '{self.bot_name}' успешно инициализирован")
        logger.info(f"🔗 Входящий URL: {self.incoming_url[:50]}...")

    def _setup_knowledge_base(self) -> Dict:
        """Загрузка базы знаний из внешнего файла"""
        try:
            # Попробуем импортировать базу знаний из отдельного файла
            import knowledge_base
            importlib.reload(knowledge_base)  # Перезагружаем модуль на случай изменений
            logger.info("✅ База знаний успешно загружена из knowledge_base.py")
            return knowledge_base.knowledge_base
        except ImportError as e:
            logger.error(f"❌ Ошибка загрузки базы знаний: {e}")
            logger.warning("⚠️ Используется встроенная база знаний по умолчанию")
            
            # Возвращаем минимальную базовую базу знаний на случай ошибки
            return {
                'dsm': {
                    'name': 'DSM',
                    'keywords': ['dsm', 'дискстэйшн', 'панель управления'],
                    'response': """🖥️ **DSM (DiskStation Manager)**""",
                    'questions': [
                        {"question": "Как настроить DSM?", "answer": "Для настройки DSM перейдите в Центр управления → Система → Общие настройки."}
                    ]
                }
            }
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при загрузке базы знаний: {e}")
            return {}

    def _normalize_text(self, text: str) -> str:
        """Нормализация текста для лучшего распознавания"""
        # Приведение к нижнему регистру
        text = text.lower()
        
        # Удаление лишних символов и пробелов
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def send_message(self, text: str, user_id: Optional[str] = None, 
                    channel: Optional[str] = None) -> bool:
        
        payload_data = {
            "text": text,
            "user_ids": [user_id] if user_id else [],
            "channel": channel if channel else ""
        }
        
        payload = {
            "payload": json.dumps(payload_data)
        }
        
        try:
            session = requests.Session()
            session.verify = False
            
            logger.info(f"📤 Отправка сообщения в Synology Chat...")
            
            response = session.post(
                self.incoming_url,
                data=payload,
                timeout=30,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            logger.info(f"📊 Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("✅ Сообщение успешно отправлено")
                return True
            else:
                logger.error(f"❌ HTTP-ошибка: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            return False

    def _update_request_category(self, request_id: int, category: str):
        """Обновление категории запроса в базе данных"""
        conn = sqlite3.connect(self.stats_db.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE user_requests 
            SET category = ? 
            WHERE id = ?
        ''', (category, request_id))
        
        conn.commit()
        conn.close()
        logger.info(f"📊 Обновлена категория запроса {request_id} на '{category}'")

    def get_main_menu(self):
        """Главное меню с категориями"""
        categories = list(self.knowledge_base.keys())
        menu_text = """👋 **Добро пожаловать в ИнструкторБот!** 🤖

**Выберите категорию, введя цифру:**

"""
        for i, category_key in enumerate(categories, 1):
            category = self.knowledge_base[category_key]
            menu_text += f"{i}. 🖥️ **{category['name']}**\n"
        
        menu_text += "\n**Введите цифру от 1 до 5 для выбора категории**"
        return menu_text

    def get_category_questions(self, category_key):
        """Меню с вопросами выбранной категории"""
        category = self.knowledge_base[category_key]
        questions = category['questions']
        
        menu_text = f"""📋 **Категория: {category['name']}**

**Выберите вопрос, введя цифру:**

"""
        for i, qa in enumerate(questions, 1):
            menu_text += f"{i}. ❓ **{qa['question']}**\n"
        
        menu_text += f"\n**Введите цифру от 1 до {len(questions)} для выбора вопроса**\n"
        menu_text += "📝 Или введите 'назад' для возврата к категориям"
        return menu_text

    def get_question_answer(self, category_key, question_index):
        """Ответ на выбранный вопрос"""
        category = self.knowledge_base[category_key]
        question = category['questions'][question_index]
        
        answer_text = f"""🎯 **Вопрос:** {question['question']}

📝 **Ответ:** {question['answer']}

💡 *Для возврата к вопросам категории введите 'назад'*
📋 *Для возврата к категориям введите 'меню'*"""
        return answer_text

    def process_question(self, question: str, user_id: str = None, username: str = None) -> Dict:
        """Обработка вопросов с системой меню"""
        logger.info(f"🧠 Обработка вопроса: '{question}' от пользователя {user_id}")
        
        # Нормализация вопроса
        normalized_question = self._normalize_text(question)
        logger.info(f"📝 Нормализованный вопрос: '{normalized_question}'")
        
        # Логирование запроса (изначально без категории)
        request_id = None
        if user_id and username:
            request_id = self.stats_db.log_request(user_id, username, question, None)
        
        # Получаем или создаем сессию пользователя
        if user_id not in user_sessions:
            user_sessions[user_id] = UserSession(user_id)
        
        session = user_sessions[user_id]
        session.last_interaction = datetime.datetime.now()
        
        # Обработка специальных команд
        if normalized_question in ['меню', 'menu', 'начать', 'старт', 'start']:
            session.reset()
            response_text = self.get_main_menu()
            category = 'main_menu'
        
        elif normalized_question == 'назад':
            if session.state == 'question_selected':
                session.state = 'category_selected'
                response_text = self.get_category_questions(session.selected_category)
                category = session.selected_category
            elif session.state == 'category_selected':
                session.reset()
                response_text = self.get_main_menu()
                category = 'main_menu'
            else:
                session.reset()
                response_text = self.get_main_menu()
                category = 'main_menu'
        
        # Обработка состояний сессии
        elif session.state == 'main_menu':
            # Выбор категории по цифре
            if normalized_question.isdigit():
                choice = int(normalized_question)
                categories = list(self.knowledge_base.keys())
                
                if 1 <= choice <= len(categories):
                    session.selected_category = categories[choice - 1]
                    session.state = 'category_selected'
                    response_text = self.get_category_questions(session.selected_category)
                    category = session.selected_category
                else:
                    response_text = "❌ **Неверный выбор!**\n\n" + self.get_main_menu()
                    category = 'error'
            else:
                response_text = "❌ **Пожалуйста, введите цифру от 1 до 5**\n\n" + self.get_main_menu()
                category = 'error'
        
        elif session.state == 'category_selected':
            # Выбор вопроса по цифре
            if normalized_question.isdigit():
                choice = int(normalized_question)
                questions = self.knowledge_base[session.selected_category]['questions']
                
                if 1 <= choice <= len(questions):
                    session.selected_question = choice - 1
                    session.state = 'question_selected'
                    response_text = self.get_question_answer(session.selected_category, session.selected_question)
                    category = session.selected_category
                else:
                    response_text = f"❌ **Неверный выбор!**\n\n" + self.get_category_questions(session.selected_category)
                    category = 'error'
            else:
                response_text = f"❌ **Пожалуйста, введите цифру от 1 до {len(self.knowledge_base[session.selected_category]['questions'])}**\n\n" + self.get_category_questions(session.selected_category)
                category = 'error'
        
        elif session.state == 'question_selected':
            # В состоянии ответа на вопрос ждем команды 'назад' или 'меню'
            response_text = "❌ **Неизвестная команда**\n\n" + self.get_question_answer(session.selected_category, session.selected_question)
            category = session.selected_category
        
        else:
            session.reset()
            response_text = self.get_main_menu()
            category = 'main_menu'
        
        if request_id and category != 'error':
            self._update_request_category(request_id, category)
        
        if request_id:
            self.stats_db.log_response(request_id, response_text, category)
        
        return {'text': response_text, 'category': category}

# Инициализация бота
bot = SynologyChatBot()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        logger.info("🌐 Получен запрос на webhook")
        
        data = request.form
        
        if not data:
            logger.error("❌ Данные формы не получены")
            return jsonify({"error": "Данные не получены"}), 400
        
        logger.info(f"📋 Полученные данные формы: {dict(data)}")
        
        message_text = data.get('text', '').strip()
        user_id = data.get('user_id')
        channel = data.get('channel_name')
        username = data.get('username', 'Неизвестный пользователь')
        
        if not message_text:
            logger.warning("⚠️ В сообщении нет текста")
            return jsonify({"error": "В сообщении нет текста"}), 400
        
        logger.info(f"👤 Сообщение от {username} ({user_id}): '{message_text}'")
        
        response_data = bot.process_question(message_text, user_id, username)
        
        success = bot.send_message(
            response_data['text'], 
            user_id, 
            channel
        )
        
        if success:
            logger.info(f"✅ Ответ успешно отправлен пользователю {username}")
            return jsonify({
                "status": "success", 
                "message": "Ответ отправлен",
                "category": response_data.get('category', 'unknown')
            })
        else:
            logger.error(f"❌ Не удалось отправить ответ пользователю {username}")
            return jsonify({"error": "Не удалось отправить ответ"}), 500
            
    except Exception as e:
        logger.error(f"💥 Критическая ошибка обработки webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    logger.info("🔍 Проверка здоровья сервиса")
    return render_template('health.html', 
                         bot_name=bot.bot_name,
                         uptime=format_timedelta(datetime.datetime.now() - start_time),
                         port=bot.port,
                         title='Проверка здоровья')

@app.route('/test', methods=['GET'])
def test_bot():
    logger.info("🧪 Запуск тестового сообщения")
    return render_template('test.html',
                         bot_name=bot.bot_name,
                         port=bot.port,
                         uptime=format_timedelta(datetime.datetime.now() - start_time),
                         title='Тест отправки')

@app.route('/stats', methods=['GET'])
def statistics():
    logger.info("📊 Запрос статистики бота")
    stats = bot.stats_db.get_statistics()
    return render_template('stats.html',
                         stats=stats,
                         bot_name=bot.bot_name,
                         uptime=format_timedelta(datetime.datetime.now() - start_time),
                         title='Статистика')

@app.route('/', methods=['GET'])
def index():
    logger.info("🏠 Запрос главной страницы")
    return render_template('index.html',
                         bot_name=bot.bot_name,
                         uptime=format_timedelta(datetime.datetime.now() - start_time),
                         port=bot.port,
                         title='Главная')
                         
@app.route('/send_test', methods=['POST'])
def send_test_message():
    message = request.form.get('message', 'Тестовое сообщение')
    logger.info(f"🧪 Отправка тестового сообщения: '{message}'")
    
    success = bot.send_message(f"🎉 **Тестовое сообщение:**\n\n{message}")
    
    if success:
        return render_template('test.html',
                             bot_name=bot.bot_name,
                             port=bot.port,
                             uptime=format_timedelta(datetime.datetime.now() - start_time),
                             title='Тест отправки',
                             message="✅ Тестовое сообщение отправлено успешно!")
    else:
        return render_template('test.html',
                             bot_name=bot.bot_name,
                             port=bot.port,
                             uptime=format_timedelta(datetime.datetime.now() - start_time),
                             title='Тест отправки',
                             message="❌ Ошибка отправки тестового сообщения")
                             
@app.route('/api/category-stats', methods=['GET'])
def api_category_stats():
    stats = bot.stats_db.get_statistics()
    return jsonify({
        'category_stats': [
            {
                'category': category,
                'count': count
            }
            for category, count in stats['category_stats']
        ]
    })

templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
os.makedirs(templates_dir, exist_ok=True)

start_time = datetime.datetime.now()

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('DEBUG_MODE', 'True').lower() == 'true'
    
    logger.info(f"🚀 Запуск {bot.bot_name} на {host}:{port}")
    logger.info(f"🌐 Webhook конечная точка: http://{host}:{port}/webhook")
    logger.info(f"🔍 Проверка работоспособности: http://{host}:{port}/health")
    logger.info(f"🧪 Тест конечной точки: http://{host}:{port}/test")
    logger.info(f"📊 Статистика: http://{host}:{port}/stats")
    logger.info(f"🏠 Главная страница: http://{host}:{port}/")
    
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        logger.info(f"🌐 Локальный IP адрес: http://{local_ip}:{port}")
        logger.info(f"🌐 Доступ с других компьютеров: http://{local_ip}:{port}")
    except Exception as e:
        logger.info(f"⚠️ Не удалось определить локальный IP адрес: {e}")
    

    app.run(host=host, port=port, debug=debug, threaded=True)
