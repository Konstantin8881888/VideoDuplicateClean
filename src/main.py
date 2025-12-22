import cmd
import os
import sys
import json
import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QFileDialog, QTextEdit, QProgressBar, QTabWidget, QHBoxLayout,
    QLineEdit, QMessageBox, QScrollArea, QCheckBox, QSpinBox, QDialog, QComboBox, QListWidget, QListWidgetItem,
)

from PyQt6.QtCore import QThread, pyqtSignal, QUrl, Qt
from PyQt6.QtGui import QIcon

# импорты наших модулей
from src.core.file_scanner import FileScanner
from src.core.frame_extractor import FrameExtractor
from src.core.optimized_comparator import OptimizedVideoComparator
from src.core.video_comparator import VideoComparator
from src.config import Config
from src.algorithms import create_algorithm


# =============================================================================
# КЛАССЫ ДЛЯ МНОГОПОТОЧНОСТИ
# =============================================================================

class OptimizedScanThread(QThread):
    """Поток для оптимизированного сканирования всех папок"""

    # Сигналы для обновления UI из потока
    progress_signal = pyqtSignal(int, str)  # прогресс (проценты, сообщение)
    result_signal = pyqtSignal(list)  # финальные результаты
    finished_signal = pyqtSignal()  # завершение работы

    def __init__(self, comparator, folder_paths, similarity_threshold=None):
        """
        Инициализация потока

        Args:
            comparator: объект для сравнения видео
            folder_paths: ОДНА папка (str) или СПИСОК папок (list)
            similarity_threshold: порог схожести
        """
        super().__init__()
        self.comparator = comparator
        # Делаем всегда списком, даже если передали одну папку
        if isinstance(folder_paths, str):
            self.folder_paths = [folder_paths]
        else:
            self.folder_paths = folder_paths
        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else Config.SIMILARITY_THRESHOLD
        self.scanner = FileScanner()

    def run(self):
        """Основной метод, который выполняется в потоке"""
        try:
            all_video_files = []
            total_folders = len(self.folder_paths)

            # ШАГ 1: Собираем ВСЕ видео из ВСЕХ папок
            for i, folder in enumerate(self.folder_paths, 1):
                progress = int((i - 1) / total_folders * 40)  # первые 40% на сбор файлов
                self.progress_signal.emit(
                    progress,
                    f"Сканирую папку {i}/{total_folders}: {os.path.basename(folder)}"
                )

                # Находим видео в текущей папке
                video_files = self.scanner.find_video_files(folder)
                all_video_files.extend(video_files)

                self.progress_signal.emit(
                    progress + 5,
                    f"Папка {i}: найдено {len(video_files)} видео"
                )

            if not all_video_files:
                self.result_signal.emit([])
                return

            self.progress_signal.emit(50, f"Всего найдено {len(all_video_files)} видеофайлов")

            # ШАГ 2: Ищем похожие видео среди ВСЕХ собранных файлов
            self.progress_signal.emit(60, "Анализирую схожесть видео...")

            similar_pairs = self.comparator.find_similar_videos_optimized(
                all_video_files,
                self.similarity_threshold
            )

            # ----- ДЕДУПЛИКАЦИЯ ПАР -----
            seen = set()
            unique_pairs = []
            for video1, video2, similarity, details in similar_pairs:
                key = tuple(sorted([video1, video2]))
                if key not in seen:
                    seen.add(key)
                    unique_pairs.append((video1, video2, similarity, details))
            similar_pairs = unique_pairs
            print(f"DEBUG: после дедупликации осталось {len(similar_pairs)} уникальных пар")
            # ---------------------------

            self.progress_signal.emit(90, f"Анализ завершен")

            # Отправляем результаты в основной поток
            self.result_signal.emit(similar_pairs)

            self.progress_signal.emit(100, "Передаю результаты для фильтрации")

        except Exception as e:
            print(f"Ошибка в потоке сканирования: {e}")
            import traceback
            traceback.print_exc()
            self.result_signal.emit([])
        finally:
            self.finished_signal.emit()


class CompareThread(QThread):
    result_signal = pyqtSignal(dict)

    def __init__(self, comparator, video1_path, video2_path, max_frames=10):
        super().__init__()
        self.comparator = comparator
        self.video1_path = video1_path
        self.video2_path = video2_path
        self.max_frames = int(max_frames or 10)

    def run(self):
        """
        Теперь сравнение для нестандартных алгоритмов выполняется в отдельном процессе
        через src/algorithms/compare_worker.py. Это защищает GUI от падений нативных библиотек.
        """
        result = None
        # если мы в CompareThread (compare-tab) — предпочитаем парное сравнение по кадрам
        try:
            from src.core.frame_extractor import FrameExtractor
            from src.algorithms.comparison_manager import ComparisonManager
            extractor = FrameExtractor()
            manager = ComparisonManager()

            frames1 = extractor.extract_frames(self.video1_path, self.max_frames)
            frames2 = extractor.extract_frames(self.video2_path, self.max_frames)

            frame_comparisons = []
            total = 0.0
            valid = 0
            for i in range(self.max_frames):
                f1 = frames1[i] if i < len(frames1) else None
                f2 = frames2[i] if i < len(frames2) else None
                if f1 is not None and f2 is not None:
                    cmp_res = manager.compare_images(f1, f2)
                    overall = cmp_res.get('overall', 0.0)
                    frame_comparisons.append({'similarity': overall, 'algorithm_details': cmp_res})
                    total += overall
                    valid += 1
                else:
                    frame_comparisons.append({'similarity': 0.0, 'algorithm_details': {}})

            overall_similarity = (total / valid) if valid > 0 else 0.0
            result = {'similarity': overall_similarity, 'frame_comparisons': frame_comparisons}
            self.result_signal.emit(result)
            return
        except Exception as e:
            # если что-то упало — логируем и пробуем стандартный путь (worker)
            import traceback
            tb = traceback.format_exc()
            # не падаем — пробуем run через subprocess дальше
            # но включим diagnostic info
            fallback_error_info = f"frame_based_compare_failed: {e}\n{tb}"

            # Для остальных алгоритмов запускаем worker в отдельном процессе
            import subprocess, json, sys, os, shlex

            # Путь к worker-скрипту (src/algorithms/compare_worker.py). main.py лежит в src/
            # script_path: .../src/algorithms/compare_worker.py
            script_path = os.path.join(os.path.dirname(__file__), 'algorithms', 'compare_worker.py')

            # определим project_root = папка выше src
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                        '..'))  # if __file__ is .../repo/src/main.py -> parent is .../repo/src
            project_root = os.path.abspath(os.path.join(project_root, '..'))  # now .../repo

            python_exe = sys.executable

            # запускаем в project_root, чтобы worker мог импортировать src.*
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root, timeout=600)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                result = {
                    'similarity': 0.0,
                    'error': f'subprocess_run_exception: {e}',
                    'traceback': tb,
                    'frame_comparisons': []
                }
                self.result_signal.emit(result)
                return

            except Exception as e:
                # например TimeoutExpired или OSError
                result = {'similarity': 0.0, 'error': f'subprocess_run_exception: {e}', 'frame_comparisons': []}
                self.result_signal.emit(result)
                return

            if proc.returncode != 0:
                err_text = proc.stderr.strip() if proc.stderr else f'returncode_{proc.returncode}'
                # включаем также stdout для диагностики
                result = {
                    'similarity': 0.0,
                    'error': f'worker_failed: {err_text}',
                    'raw_stdout': proc.stdout,
                    'raw_stderr': proc.stderr,
                    'frame_comparisons': []
                }
                self.result_signal.emit(result)
                return

            # Парсим stdout JSON
            out_text = proc.stdout.strip()
            try:
                result = json.loads(out_text) if out_text else {'similarity': 0.0, 'frame_comparisons': []}
            except Exception as e:
                result = {'similarity': 0.0, 'error': f'json_parse_error: {e}', 'raw_stdout': out_text,
                          'frame_comparisons': []}

        except Exception as e:
            result = {'similarity': 0.0, 'error': f'unhandled_exception_in_compare_thread: {e}',
                      'frame_comparisons': []}

        # Отправляем результат в основной поток
        self.result_signal.emit(result)

# =============================================================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ
# =============================================================================
def resource_path(relative_path):
    """Получает абсолютный путь к ресурсу (ДЛЯ БЕЛКИ НА ИКОНКЕ), работает для dev и для PyInstaller"""
    try:
        # PyInstaller создаёт временную папку и хранит путь в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoDuplicate Cleaner")
        self.setGeometry(30, 50, 1100, 800)  # Увеличили высоту окна

        icon_path = resource_path("static/logo.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.log_counter = 0
        # Инициализация компонентов
        self.scanner = FileScanner()
        self.frame_extractor = FrameExtractor()
        self.comparator = create_algorithm('simple')
        self.current_algorithm_name = 'simple'

        self.pairs_widget = QWidget()
        self.pairs_layout = QVBoxLayout(self.pairs_widget)

        # Создаем интерфейс
        self.setup_ui()

        # Переменные состояния
        self.selected_folders = []  # ← список папок

        # Чёрный список папок (не сканировать)
        self.excluded_folders = []
        self.excluded_folders_file = "excluded_folders.json"
        self.load_excluded_folders()  # ← загружаем при старте

        self.video1_path = ""
        self.video2_path = ""
        self.current_pairs = []
        self.optimized_scan_thread = None
        self.compare_thread = None
        self.marked_for_deletion = set()  # Файлы, отмеченные для удаления
        self.pair_widgets = {}  # Виджеты пар для управления чекбоксами

        # Атрибуты для управления кнопками пар
        self.pairs_container = None
        #self.pairs_layout = None



    def safe_log(self, message):
        """Безопасное логирование с защитой от рекурсии"""
        self.log_counter += 1
        if self.log_counter > 1000:  # защита от бесконечного цикла
            print(f"ERROR: Too many log calls: {message}")
            return
        self.log_text.append(message)

    def setup_ui(self):
        """Создает весь пользовательский интерфейс"""
        # Создаем вкладки
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Создаем и добавляем вкладки
        self.scan_tab = self.create_scan_tab()
        self.compare_tab = self.create_compare_tab()

        self.tabs.addTab(self.scan_tab, "📁 Сканирование папки")
        self.tabs.addTab(self.compare_tab, "🔍 Сравнение видео")

        self.on_scan_algorithm_changed(self.algorithm_combo.currentIndex())
        self.on_compare_algorithm_changed(self.compare_algorithm_combo.currentIndex())

    def create_algorithm_instance_from_ui(self, alg_name, context='scan'):
        """
        Создаёт и конфигурирует экземпляр алгоритма по имени alg_name.
        context: 'scan' или 'compare' — чтобы брать параметры с нужной вкладки.
        """
        alg = create_algorithm(alg_name)
        # Если phash — установим параметры из UI соответствующей вкладки
        try:
            if alg_name == 'phash' and getattr(alg, 'implemented', False):
                if context == 'scan':
                    if hasattr(self, 'phash_frames_spin'):
                        alg.frames_to_sample = int(self.phash_frames_spin.value())
                    if hasattr(self, 'phash_ham_spin'):
                        alg.ham_thresh = int(self.phash_ham_spin.value())
                elif context == 'compare':
                    if hasattr(self, 'compare_phash_frames_spin'):
                        alg.frames_to_sample = int(self.compare_phash_frames_spin.value())
                    if hasattr(self, 'compare_phash_ham_spin'):
                        alg.ham_thresh = int(self.compare_phash_ham_spin.value())
        except Exception:
            pass
        return alg

    def create_scan_tab(self):
        """Создает вкладку для сканирования папки с прокруткой и управлением удалением"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Заголовок с выделением цветом
        title_text = "Поиск похожих видеофайлов в папке. "
        formats_text = "Доступные форматы: .mp4, .avi, .mov, .mkv, .wmv"

        title_label = QLabel()
        title_label.setTextFormat(Qt.TextFormat.RichText)
        title_label.setText(
            f"{title_text}<span style='color: #E67E22; font-weight: bold;'>{formats_text}</span>"

        )
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title_label)

        # Выбор папки
        folder_layout = QHBoxLayout()
        self.select_button = QPushButton("Выбрать папку для сканирования")
        self.select_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.select_button)

        self.selected_folder_label = QLabel("Папки не выбраны")
        folder_layout.addWidget(self.selected_folder_label)
        layout.addLayout(folder_layout)

        # Растягивающийся элемент
        folder_layout.addStretch()

        # Кнопка лицензии
        self.license_button = QPushButton("📜 Ознакомиться с лицензией")
        self.license_button.clicked.connect(self.show_license)
        self.license_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 5px 10px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        folder_layout.addWidget(self.license_button)

        # ВТОРОЙ РЯД: Управление списком папок
        folder_control_layout = QHBoxLayout()

        # Пустое пространство слева
        folder_control_layout.addStretch()

        # Кнопка запрета сканирования папки
        self.exclude_folder_btn = QPushButton("🚫 Включить папку в чёрный список")
        self.exclude_folder_btn.clicked.connect(self.exclude_folder)
        self.exclude_folder_btn.setToolTip("Добавить папку в чёрный список (не сканировать)")
        self.exclude_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffecb3;
                border: 1px solid #ffd54f;
                padding: 5px 10px;
                font-size: 9pt;
                margin-right: 5px;
            }
            QPushButton:hover {
                background-color: #ffd54f;
            }
        """)
        folder_control_layout.addWidget(self.exclude_folder_btn)

        # Редактирование ЧС
        self.manage_excluded_btn = QPushButton("📋 Управление чёрным списком")
        self.manage_excluded_btn.clicked.connect(self.manage_excluded_folders)
        self.manage_excluded_btn.setToolTip("Управление чёрным списком папок")
        self.manage_excluded_btn.setStyleSheet("""
            QPushButton {
                background-color: #e3f2fd;
                border: 1px solid #bbdefb;
                padding: 5px 10px;
                font-size: 9pt;
                margin-right: 5px;
            }
            QPushButton:hover {
                background-color: #bbdefb;
            }
        """)
        folder_control_layout.addWidget(self.manage_excluded_btn)

        # Кнопка удаления последней папки
        self.remove_last_btn = QPushButton("↶ Удалить последнюю папку")
        self.remove_last_btn.clicked.connect(self.remove_last_folder)
        self.remove_last_btn.setToolTip("Удалить последнюю добавленную папку")
        self.remove_last_btn.setStyleSheet("""
            QPushButton {
                background-color: #fff3cd;
                border: 1px solid #ffeaa7;
                padding: 5px 10px;
                font-size: 9pt;
                margin-right: 5px;
            }
            QPushButton:hover {
                background-color: #ffeaa7;
            }
        """)
        self.remove_last_btn.setEnabled(False)
        folder_control_layout.addWidget(self.remove_last_btn)

        # Кнопка очистки всех папок
        self.clear_folders_btn = QPushButton("🗑️ Очистить список")
        self.clear_folders_btn.clicked.connect(self.clear_folders)
        self.clear_folders_btn.setToolTip("Очистить весь список выбранных папок")
        self.clear_folders_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffebee;
                border: 1px solid #ffcdd2;
                padding: 5px 10px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #ffcdd2;
            }
        """)
        self.clear_folders_btn.setEnabled(False)
        folder_control_layout.addWidget(self.clear_folders_btn)

        layout.addLayout(folder_control_layout)


        # Настройки сканирования
        settings_layout = QHBoxLayout()

        # --- выбор алгоритма (добавлено) ---
        settings_layout.addWidget(QLabel("Алгоритм:"))
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems([
            "Simple (original)",
            "pHash (fast)",
            "CNN+Faiss (advanced) — (пока не реализован)"
        ])
        self.algorithm_combo.setCurrentIndex(0)
        # при смене алгоритма обновляем comparator
        self.algorithm_combo.currentIndexChanged.connect(self.on_scan_algorithm_changed)
        settings_layout.addWidget(self.algorithm_combo)
        # --- конец блока ---

        # --- добавляем контролы pHash (количество кадров и порог) ---
        self.phash_frames_label = QLabel("pHash frames:")
        settings_layout.addWidget(self.phash_frames_label)
        self.phash_frames_spin = QSpinBox()
        self.phash_frames_spin.setRange(1, 500)
        self.phash_frames_spin.setValue(getattr(Config, 'PHASH_FRAMES', 30))  # sensible default
        self.phash_frames_spin.setMaximumWidth(70)
        settings_layout.addWidget(self.phash_frames_spin)

        self.phash_ham_label = QLabel("pHash ham:")
        settings_layout.addWidget(self.phash_ham_label)
        self.phash_ham_spin = QSpinBox()
        self.phash_ham_spin.setRange(1, 64)
        self.phash_ham_spin.setValue(getattr(Config, 'PHASH_HAMMING_THRESHOLD', 12))
        self.phash_ham_spin.setMaximumWidth(70)
        settings_layout.addWidget(self.phash_ham_spin)
        # --- конец блока --

        settings_layout.addWidget(QLabel("Порог схожести:"))
        self.similarity_threshold_input = QLineEdit(str(Config.SIMILARITY_THRESHOLD))
        self.similarity_threshold_input.setMaximumWidth(50)
        settings_layout.addWidget(self.similarity_threshold_input)

        settings_layout.addWidget(QLabel("(0.1 - 1.0, где 1.0 = идентичные)"))
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        # Кнопка запуска сканирования
        self.scan_button = QPushButton("🚀 Начать оптимизированное сканирование")
        self.scan_button.clicked.connect(self.start_optimized_scan)
        self.scan_button.setStyleSheet("QPushButton { font-weight: bold; padding: 8px; }")
        layout.addWidget(self.scan_button)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # КОМПАКТНАЯ панель управления удалением с ОБЩИМ РАЗМЕРОМ
        deletion_panel = QWidget()
        deletion_panel.setStyleSheet("""
               QWidget {
                   background-color: #fff3cd;
                   border: 1px solid #ffeaa7;
                   border-radius: 5px;
                   padding: 8px;
                   margin: 3px;
               }
           """)
        deletion_layout = QVBoxLayout()  # Возвращаем вертикальный layout
        deletion_panel.setLayout(deletion_layout)
        deletion_panel.setMaximumHeight(100)  # Немного увеличиваем высоту для двух строк

        # Верхняя строка: статистика
        stats_layout = QHBoxLayout()

        self.marked_count_label = QLabel("📊 Отмечено: 0 файлов")
        self.marked_count_label.setStyleSheet("font-weight: bold; color: #856404; font-size: 9pt;")
        stats_layout.addWidget(self.marked_count_label)

        stats_layout.addStretch()

        self.total_size_label = QLabel("💾 Общий размер: 0 MB")
        self.total_size_label.setStyleSheet("color: #856404; font-size: 9pt;")
        stats_layout.addWidget(self.total_size_label)

        deletion_layout.addLayout(stats_layout)

        # Нижняя строка: кнопки управления
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)

        self.clear_marks_btn = QPushButton("Очистить отметки")
        self.clear_marks_btn.clicked.connect(self.clear_all_marks)
        self.clear_marks_btn.setStyleSheet("""
               QPushButton {
                   background-color: #95a5a6;
                   color: white;
                   padding: 4px 8px;
                   border-radius: 3px;
                   font-size: 9pt;
               }
               QPushButton:hover {
                   background-color: #7f8c8d;
               }
           """)
        buttons_layout.addWidget(self.clear_marks_btn)

        self.delete_marked_btn = QPushButton("🗑️ УДАЛИТЬ ОТМЕЧЕННЫЕ")
        self.delete_marked_btn.clicked.connect(self.delete_marked_files)
        self.delete_marked_btn.setStyleSheet("""
               QPushButton {
                   background-color: #e74c3c;
                   color: white;
                   font-weight: bold;
                   padding: 6px 12px;
                   border-radius: 4px;
                   font-size: 9pt;
               }
               QPushButton:hover {
                   background-color: #c0392b;
               }
               QPushButton:disabled {
                   background-color: #bdc3c7;
                   color: #7f8c8d;
               }
           """)
        self.delete_marked_btn.setEnabled(False)
        buttons_layout.addWidget(self.delete_marked_btn)

        deletion_layout.addLayout(buttons_layout)
        layout.addWidget(deletion_panel)

        # Поле для логов и результатов
        self.log_text = QTextEdit()
        self.log_text.setPlaceholderText(
            "Здесь будут отображаться процесс сканирования и результаты..."
        )
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

        # Заголовок для списка пар
        pairs_label = QLabel("🎯 Найденные пары для сравнения:")
        pairs_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(pairs_label)

        # Добавляем пояснение
        # Создаем контейнер для плашки с крестиком
        warning_widget = QWidget()
        warning_layout = QHBoxLayout(warning_widget)
        warning_layout.setContentsMargins(8, 8, 8, 8)

        # Текст предупреждения
        warning_text = QLabel(
            "💡 <span style='color: #856404; font-size: 9pt;'>"
            "Один и тот же файл может быть в нескольких парах - счётчик показывает уникальные файлы для удаления"
            "</span>"
        )
        warning_text.setWordWrap(True)
        warning_layout.addWidget(warning_text)

        # Кнопка закрытия (крестик)
        close_btn = QPushButton("×")
        close_btn.setStyleSheet("""
            QPushButton {
                color: #856404;
                font-weight: bold;
                font-size: 14pt;
                border: none;
                background: transparent;
                padding: 0px 4px;
                margin-left: 4px;
            }
            QPushButton:hover {
                background-color: #ffeaa7;
                border-radius: 3px;
            }
        """)
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(warning_widget.hide)
        warning_layout.addWidget(close_btn)

        # Стиль для всей плашки
        warning_widget.setStyleSheet(
            "background-color: #fff3cd; border-radius: 4px; border: 1px solid #ffeaa7;"
        )

        layout.addWidget(warning_widget)

        # ПРОКРУЧИВАЕМАЯ ОБЛАСТЬ ДЛЯ КНОПОК ПАР
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(400)

        # Контейнер для кнопок внутри прокрутки
        self.pairs_container = QWidget()
        self.pairs_layout = QVBoxLayout(self.pairs_container)
        scroll_area.setWidget(self.pairs_container)

        layout.addWidget(scroll_area)

        # Статусная строка
        self.status_label = QLabel("Готов к работе")
        layout.addWidget(self.status_label)

        return widget

    def create_compare_tab(self):
        """Создает вкладку для сравнения двух видео (с просмотром пары, удалением и выбором числа кадров)"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Заголовок
        title_label = QLabel("Сравнение двух видеофайлов")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title_label)

        # Выбор алгоритма сравнения
        comp_layout = QHBoxLayout()
        comp_layout.addWidget(QLabel("Алгоритм сравнения:"))
        self.compare_algorithm_combo = QComboBox()
        self.compare_algorithm_combo.addItems([
            "Simple (original)",
            "pHash (fast)",
            "CNN+Faiss (advanced) — (пока не реализован)"
        ])
        # синхронизируем с основным combobox: при смене вызываем ту же функцию
        self.compare_algorithm_combo.currentIndexChanged.connect(self.on_compare_algorithm_changed)
        comp_layout.addWidget(self.compare_algorithm_combo)

        # Добавляем блок управления pHash для compare-tab (скрываем по умолчанию)

        self.compare_phash_ham_label = QLabel("pHash ham:")
        comp_layout.addWidget(self.compare_phash_ham_label)
        self.compare_phash_ham_spin = QSpinBox()
        self.compare_phash_ham_spin.setRange(1, 64)
        self.compare_phash_ham_spin.setValue(getattr(Config, 'PHASH_HAMMING_THRESHOLD', 12))
        self.compare_phash_ham_spin.setMaximumWidth(70)
        comp_layout.addWidget(self.compare_phash_ham_spin)

        # добавляем наш comp_layout в основной layout вкладки
        # Оборачиваем HBox в контейнерный QWidget и добавляем его с левым выравниванием
        comp_container = QWidget()
        comp_container.setLayout(comp_layout)

        # Ограничим максимальную ширину комбобокса, чтобы он не растягивался слишком сильно
        self.compare_algorithm_combo.setMaximumWidth(300)  # например 300px, можно уменьшить/увеличить

        # Добавляем контейнер в основной layout с выравниванием влево
        from PyQt6.QtCore import Qt
        layout.addWidget(comp_container, alignment=Qt.AlignmentFlag.AlignLeft)

        # Выбор первого видео
        video1_layout = QHBoxLayout()
        self.select_video1_btn = QPushButton("Выбрать первое видео")
        self.select_video1_btn.clicked.connect(lambda: self.select_video_for_comparison(1))
        video1_layout.addWidget(self.select_video1_btn)

        self.video1_label = QLabel("Видео не выбрано")
        video1_layout.addWidget(self.video1_label)

        # Кнопка удаления напротив первого видео
        self.delete_video1_btn = QPushButton("🗑 Удалить видео1")
        self.delete_video1_btn.setEnabled(False)
        self.delete_video1_btn.clicked.connect(lambda: self.delete_video_file(1))
        video1_layout.addWidget(self.delete_video1_btn)

        layout.addLayout(video1_layout)

        # Выбор второго видео
        video2_layout = QHBoxLayout()
        self.select_video2_btn = QPushButton("Выбрать второе видео")
        self.select_video2_btn.clicked.connect(lambda: self.select_video_for_comparison(2))
        video2_layout.addWidget(self.select_video2_btn)

        self.video2_label = QLabel("Видео не выбрано")
        video2_layout.addWidget(self.video2_label)

        # Кнопка удаления напротив второго видео
        self.delete_video2_btn = QPushButton("🗑 Удалить видео2")
        self.delete_video2_btn.setEnabled(False)
        self.delete_video2_btn.clicked.connect(lambda: self.delete_video_file(2))
        video2_layout.addWidget(self.delete_video2_btn)

        layout.addLayout(video2_layout)

        # Настройка числа кадров для сравнения (SpinBox)
        frames_layout = QHBoxLayout()
        frames_layout.addWidget(QLabel("Кадров для сравнения:"))
        self.frame_count_spin = QSpinBox()
        self.frame_count_spin.setRange(1, 50)
        self.frame_count_spin.setValue(10)  # по умолчанию 10
        self.frame_count_spin.setMaximumWidth(80)
        frames_layout.addWidget(self.frame_count_spin)
        frames_layout.addStretch()
        layout.addLayout(frames_layout)

        # Кнопки: Просмотр пары и сравнение
        actions_layout = QHBoxLayout()

        self.view_pair_btn = QPushButton("👁️ Посмотреть пару")
        self.view_pair_btn.setEnabled(False)
        self.view_pair_btn.clicked.connect(lambda: self.open_comparison_dialog([self.video1_path, self.video2_path]))
        actions_layout.addWidget(self.view_pair_btn)

        self.compare_btn = QPushButton("🔍 Сравнить выбранные видео")
        self.compare_btn.clicked.connect(self.compare_selected_videos)
        actions_layout.addWidget(self.compare_btn)

        layout.addLayout(actions_layout)

        # Результаты сравнения
        self.compare_results = QTextEdit()
        self.compare_results.setPlaceholderText("Результаты сравнения появятся здесь...")
        self.compare_results.setReadOnly(True)
        layout.addWidget(self.compare_results)

        return widget

    def clear_folders(self):
        """Очищает список выбранных папок"""
        if not self.selected_folders:
            return

        # Подтверждение
        reply = QMessageBox.question(
            self,
            "Очистить список папок",
            f"Вы уверены, что хотите очистить список из {len(self.selected_folders)} папок?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Запоминаем для лога
            removed_count = len(self.selected_folders)
            removed_names = [os.path.basename(f) for f in self.selected_folders[:3]]

            # Очищаем список
            self.selected_folders.clear()

            # Обновляем UI
            self.selected_folder_label.setText("Папки не выбраны")
            self.clear_folders_btn.setEnabled(False)

            # Логируем
            self.log_text.append(f"🗑️ Очищен список папок ({removed_count} папок)")
            if removed_names:
                self.log_text.append(f"   Удалены: {', '.join(removed_names)}" +
                                     ("..." if removed_count > 3 else ""))

    def check_folder_nesting(self, new_folder):
        """
        Проверяет нет ли вложенности между новой папкой и уже выбранными

        Возвращает:
        - True если всё ок (нет вложенности)
        - False если есть проблема (вложенность или дублирование)
        """
        if not hasattr(self, 'selected_folders') or not self.selected_folders:
            return True

        new_folder = os.path.normpath(new_folder)

        for existing_folder in self.selected_folders:
            existing_folder = os.path.normpath(existing_folder)

            # Проверка: новая папка внутри существующей
            if new_folder.startswith(existing_folder + os.sep):
                # Находим разницу в путях для сообщения
                relative_path = os.path.relpath(new_folder, existing_folder)
                self.show_warning(
                    f"Папка '{os.path.basename(new_folder)}' уже содержится "
                    f"в выбранной папке '{os.path.basename(existing_folder)}'.\n"
                    f"Путь: {relative_path}\n\n"
                    f"Достаточно выбрать только родительскую папку."
                )
                return False

            # Проверка: существующая папка внутри новой
            if existing_folder.startswith(new_folder + os.sep):
                relative_path = os.path.relpath(existing_folder, new_folder)
                self.show_warning(
                    f"Выбранная папка '{os.path.basename(existing_folder)}' "
                    f"уже содержится в добавляемой папке '{os.path.basename(new_folder)}'.\n"
                    f"Путь: {relative_path}\n\n"
                    f"Достаточно выбрать только родительскую папку."
                )
                return False

            # Проверка: это одна и та же папка (уже обрабатывается в select_folder)
            if new_folder == existing_folder:
                return False

        return True

    def manage_excluded_folders(self):
        """Открывает диалог управления чёрным списком"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Управление чёрным списком")
        dialog.setGeometry(200, 200, 500, 400)

        layout = QVBoxLayout(dialog)

        # Заголовок
        title = QLabel(f"Чёрный список папок ({len(self.excluded_folders)}):")
        title.setStyleSheet("font-weight: bold; font-size: 11pt; margin-bottom: 10px;")
        layout.addWidget(title)

        # Список папок с прокруткой
        scroll_area = QScrollArea()
        list_widget = QListWidget()

        for folder in self.excluded_folders:
            item = QListWidgetItem(folder)
            item.setToolTip(folder)
            list_widget.addItem(item)

        scroll_area.setWidget(list_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Кнопки управления
        button_layout = QHBoxLayout()

        remove_btn = QPushButton("🗑️ Удалить выбранное")
        remove_btn.clicked.connect(lambda: self.remove_excluded_folder(list_widget, dialog))
        remove_btn.setEnabled(False)

        clear_btn = QPushButton("🗑️ Очистить всё")
        clear_btn.clicked.connect(lambda: self.clear_excluded_folders(dialog))
        clear_btn.setEnabled(bool(self.excluded_folders))

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dialog.accept)

        button_layout.addWidget(remove_btn)
        button_layout.addWidget(clear_btn)

        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Обновляем состояние кнопки удаления при выборе
        list_widget.itemSelectionChanged.connect(
            lambda: remove_btn.setEnabled(bool(list_widget.selectedItems()))
        )

        dialog.exec()

    def remove_last_folder(self):
        """Удаляет последнюю добавленную папку"""
        try:
            if not self.selected_folders:
                return

            # Удаляем папку
            last_folder = self.selected_folders.pop()
            self.log_text.append(f"↶ Удалена последняя папка: {os.path.basename(last_folder)}")

            # ОБНОВЛЯЕМ НАДПИСЬ
            if self.selected_folders:
                # Есть папки - показываем список
                label_text = f"Выбрано папок: {len(self.selected_folders)}"
                names = [os.path.basename(f) for f in self.selected_folders[-3:]]  # последние 3
                label_text += f" ({', '.join(names)}" + ("..." if len(self.selected_folders) > 3 else "") + ")"
            else:
                # Нет папок - стандартный текст
                label_text = "Папки не выбраны"

            # Устанавливаем текст НАПРЯМУЮ
            self.selected_folder_label.setText(label_text)

            # Отключаем кнопки если список пуст
            if not self.selected_folders:
                self.clear_folders_btn.setEnabled(False)
                self.remove_last_btn.setEnabled(False)

        except Exception as e:
            print(f"ERROR in remove_last_folder: {e}")
            import traceback
            traceback.print_exc()

    def exclude_folder(self):
        """Добавляет папку в чёрный список (не сканировать)"""
        try:
            folder = QFileDialog.getExistingDirectory(
                self,
                "Выберите папку для добавления в чёрный список\n(файлы в ней не будут сканироваться)"
            )

            if not folder:
                return

            folder = os.path.normpath(folder)

            # Проверяем не добавлена ли уже
            if folder in self.excluded_folders:
                QMessageBox.information(
                    self,
                    "Папка уже в чёрном списке",
                    f"Папка уже находится в чёрном списке:\n{folder}"
                )
                return

            # Показываем объяснение
            explanation = QMessageBox(self)
            explanation.setWindowTitle("Добавление в чёрный список")
            explanation.setText(f"Добавить папку в чёрный список?\n\n{folder}")
            explanation.setInformativeText(
                "Файлы в этой папке и всех её подпапках НЕ будут сканироваться.\n"
                "Это полезно при высокой сложности дерева папок.\n"
                "Чёрный список сохраняется между запусками программы."
            )
            explanation.setStandardButtons(
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
            )
            explanation.setDefaultButton(QMessageBox.StandardButton.No)

            if explanation.exec() == QMessageBox.StandardButton.Yes:
                self.excluded_folders.append(folder)
                self.save_excluded_folders()

                self.log_text.append(f"🚫 Папка добавлена в чёрный список: {os.path.basename(folder)}")
                self.log_text.append(f"   Полный путь: {folder}")

                QMessageBox.information(
                    self,
                    "Папка добавлена",
                    f"Папка добавлена в чёрный список.\n\n"
                    f"Теперь при сканировании будут пропускаться все файлы в:\n{folder}"
                )

        except Exception as e:
            print(f"ERROR in exclude_folder: {e}")
            import traceback
            traceback.print_exc()

    def save_excluded_folders(self):
        """Сохраняет чёрный список папок в файл"""
        try:
            with open(self.excluded_folders_file, 'w', encoding='utf-8') as f:
                json.dump(self.excluded_folders, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"ERROR saving excluded folders: {e}")

    def load_excluded_folders(self):
        """Загружает чёрный список папок из файла"""
        try:
            if os.path.exists(self.excluded_folders_file):
                with open(self.excluded_folders_file, 'r', encoding='utf-8') as f:
                    self.excluded_folders = json.load(f)
                    if self.excluded_folders:
                        self.log_text.append(f"📋 Загружен чёрный список: {len(self.excluded_folders)} папок")
        except Exception as e:
            print(f"ERROR loading excluded folders: {e}")
            self.excluded_folders = []

    def remove_excluded_folder(self, list_widget, dialog):
        """Удаляет выбранную папку из чёрного списка"""
        selected = list_widget.selectedItems()
        if not selected:
            return

        folder_to_remove = selected[0].text()

        reply = QMessageBox.question(
            dialog,
            "Удаление из чёрного списка",
            f"Удалить папку из чёрного списка?\n\n{folder_to_remove}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if folder_to_remove in self.excluded_folders:
                self.excluded_folders.remove(folder_to_remove)
                self.save_excluded_folders()

                # Обновляем список
                list_widget.takeItem(list_widget.row(selected[0]))

                self.log_text.append(f"📋 Удалена из чёрного списка: {os.path.basename(folder_to_remove)}")

    def clear_excluded_folders(self, dialog):
        """Очищает весь чёрный список"""
        if not self.excluded_folders:
            return

        reply = QMessageBox.question(
            dialog,
            "Очистка чёрного списка",
            f"Очистить весь чёрный список ({len(self.excluded_folders)} папок)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.excluded_folders.clear()
            self.save_excluded_folders()
            dialog.accept()
            self.log_text.append("📋 Чёрный список полностью очищен")


    def show_license(self):
        """Показывает окно с текстом лицензии"""

        # Создаем диалоговое окно
        dialog = QDialog(self)
        dialog.setWindowTitle("VideoDuplicate Cleaner - Лицензионное соглашение")
        dialog.setGeometry(200, 200, 700, 500)

        layout = QVBoxLayout(dialog)

        # Заголовок
        title_label = QLabel("Актуальный текст лицензионного соглашения:")
        title_label.setStyleSheet("font-weight: bold; font-size: 11pt; margin: 10px;")
        layout.addWidget(title_label)

        # Поле с текстом лицензии
        license_text = QTextEdit()
        license_text.setReadOnly(True)

        # Используем существующую функцию load_license_text()
        license_content = load_license_text()  # ← вызов существующей функции!
        license_text.setPlainText(license_content)

        layout.addWidget(license_text)

        # Кнопка закрытия
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(dialog.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Показать окно
        dialog.exec()

    def clear_all_marks(self):
        """Очищает все отметки удаления"""
        if not self.marked_for_deletion:
            return

        reply = QMessageBox.question(
            self,
            "Очистка отметок",
            "Вы уверены, что хотите очистить все отметки удаления?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.marked_for_deletion.clear()
            for cb_list in self.pair_widgets.values():
                for checkbox in cb_list:
                    if checkbox:
                        checkbox.setChecked(False)
            self.update_deletion_ui()
            self.log_text.append("✅ Все отметки удаления очищены")

    # =============================================================================
    # МЕТОДЫ ДЛЯ ВКЛАДКИ СКАНИРОВАНИЯ
    # =============================================================================

    def select_folder(self):
        """Выбирает папку для сканирования"""
        try:
            folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
            print(f"DEBUG: Selected folder: {folder}")

            if folder:
                # Проверяем что атрибут существует
                if not hasattr(self, 'selected_folders'):
                    self.selected_folders = []  # создаём если нет
                    print("DEBUG: Created selected_folders list")

                # Проверяем дубликат
                if folder not in self.selected_folders:
                    # ДОБАВЛЯЕМ новую папку
                    self.selected_folders.append(folder)
                    print(f"DEBUG: Added folder. Total: {len(self.selected_folders)}")

                    # Обновляем метку
                    label_text = f"Выбрано папок: {len(self.selected_folders)}"
                    if self.selected_folders:
                        names = [os.path.basename(f) for f in self.selected_folders[-3:]]  # последние 3
                        label_text += f" ({', '.join(names)}" + ("..." if len(self.selected_folders) > 3 else "") + ")"

                    self.selected_folder_label.setText(label_text)

                    # ВКЛЮЧАЕМ кнопки очистки
                    self.clear_folders_btn.setEnabled(True)
                    self.remove_last_btn.setEnabled(True)

                    self.log_text.append(f"📁 Добавлена папка: {os.path.basename(folder)}")
                else:
                    # ПАПКА УЖЕ В СПИСКЕ
                    print("DEBUG: Folder already in list")
                    self.log_text.append(f"⚠ Папка уже в списке: {os.path.basename(folder)}")

                # 2. Проверка на вложенность с уже выбранными папками
                if not self.check_folder_nesting(folder):
                    return  # не добавляем папку

            else:
                # Пользователь отменил выбор (folder = "")
                print("DEBUG: User cancelled folder selection")


        except Exception as e:
            print(f"ERROR in select_folder: {e}")
            import traceback
            traceback.print_exc()


    def start_optimized_scan(self):
        """Запускает оптимизированное сканирование всех выбранных папок"""
        try:
            print(f"DEBUG: Starting scan with folders: {self.selected_folders}")

            if not self.selected_folders:
                self.show_warning("Сначала выберите хотя бы одну папку для сканирования!")
                return

            # Проверка порога
            try:
                threshold_text = self.similarity_threshold_input.text()
                threshold = float(threshold_text) if threshold_text else Config.SIMILARITY_THRESHOLD
                if not (0.1 <= threshold <= 1.0):
                    raise ValueError("Порог должен быть между 0.1 и 1.0")
            except ValueError as e:
                self.show_warning(f"Некорректный порог схожести: {e}")
                return

            print(f"DEBUG: Threshold: {threshold}")

            # Блокируем UI на время сканирования
            self.set_scan_ui_enabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)

            # Очищаем предыдущие результаты
            self.clear_pair_buttons()
            self.log_text.clear()

            self.log_text.append("🚀 ЗАПУСК ОПТИМИЗИРОВАННОГО СКАНИРОВАНИЯ")
            for i, folder in enumerate(self.selected_folders, 1):
                self.log_text.append(f"📁 Папка {i}: {folder}")
            self.log_text.append(f"🎯 Порог схожести: {threshold:.0%}")
            self.log_text.append(f"📊 Всего папок: {len(self.selected_folders)}")
            self.log_text.append("─" * 50)

            print(f"DEBUG: Creating OptimizedScanThread...")

            # Запускаем поток
            # перед созданием потока — определяем имя алгоритма из combobox на вкладке Scan
            mapping = {0: 'simple', 1: 'phash', 2: 'cnn_faiss'}
            alg_index = self.algorithm_combo.currentIndex()
            alg_name = mapping.get(alg_index, 'simple')
            comparator = self.create_algorithm_instance_from_ui(alg_name, context='scan')

            # далее используем comparator при создании OptimizedScanThread
            self.optimized_scan_thread = OptimizedScanThread(comparator, self.selected_folders, threshold)


            print(f"DEBUG: Connecting signals...")

            # Подключаем сигналы
            self.optimized_scan_thread.progress_signal.connect(self.update_optimized_progress)
            self.optimized_scan_thread.result_signal.connect(self.optimized_scan_finished)
            self.optimized_scan_thread.finished_signal.connect(self.scan_thread_finished)

            print(f"DEBUG: Starting thread...")
            self.optimized_scan_thread.start()

            print(f"DEBUG: Thread started successfully")

        except Exception as e:
            print(f"ERROR in start_optimized_scan: {e}")
            import traceback
            traceback.print_exc()
            # Разблокируем UI в случае ошибки
            self.set_scan_ui_enabled(True)
            self.progress_bar.setVisible(False)

    def update_optimized_progress(self, value: int, message: str):
        """Обновляет прогресс сканирования"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
        self.log_text.append(f"⚡ {message}")

    def optimized_scan_finished(self, results: list):
        """Обрабатывает результаты оптимизированного сканирования - ПОКАЗЫВАЕМ ВСЕ ПАРЫ"""
        self.log_text.append("\n" + "═" * 50)
        self.log_text.append("✅ СКАНИРОВАНИЕ ЗАВЕРШЕНО!")

        if not results:
            self.log_text.append("❌ Похожих видеофайлов не найдено")
            self.status_label.setText("Похожие видео не найдены")
            return

        # ФИЛЬТРУЕМ результаты через чёрный список
        filtered_results = self.filter_excluded_pairs(results)

        self.log_text.append(f"📊 Найдено пар похожих видео: {len(results)}")
        self.log_text.append(f"📊 После фильтрации чёрного списка осталось: {len(filtered_results)}")

        # Сохраняем пары для последующего использования
        if len(results) != len(filtered_results):
            self.log_text.append(f"🚫 Исключено пар: {len(results) - len(filtered_results)}")

        self.status_label.setText(f"Найдено {len(filtered_results)} пары похожих видео")

        # Сохраняем отфильтрованные пары
        self.current_pairs = filtered_results

        # Создаем кнопки для ОТФИЛЬТРОВАННЫХ пар
        self.create_pair_buttons(filtered_results)  # ← передаём отфильтрованные!

        # ВАЖНО: Статистику считаем по ОТФИЛЬТРОВАННЫМ парам!
        if filtered_results:
            high_similarity = sum(1 for _, _, sim, _ in filtered_results if sim > 0.8)
            medium_similarity = sum(1 for _, _, sim, _ in filtered_results if 0.6 <= sim <= 0.8)
            low_similarity = sum(1 for _, _, sim, _ in filtered_results if sim < 0.6)

            self.log_text.append(f"🎯 Высокая схожесть (>80%): {high_similarity} пар")
            self.log_text.append(f"📗 Средняя схожесть (60-80%): {medium_similarity} пар")
            self.log_text.append(f"📉 Низкая схожесть (<60%): {low_similarity} пар")
        else:
            self.log_text.append("📊 Нет пар для анализа схожести")



    def filter_excluded_pairs(self, pairs):
        """Фильтрует пары, исключая те, где файлы в чёрном списке"""
        if not hasattr(self, 'excluded_folders') or not self.excluded_folders:
            return pairs

        filtered_pairs = []
        excluded_count = 0

        for pair in pairs:
            # pair обычно имеет вид: (video1, video2, similarity, result_dict)
            video1 = pair[0] if isinstance(pair, (list, tuple)) else pair.get('file1', '')
            video2 = pair[1] if isinstance(pair, (list, tuple)) else pair.get('file2', '')

            # Проверяем оба файла
            file1_excluded = self.is_file_excluded(video1)
            file2_excluded = self.is_file_excluded(video2)

            if not file1_excluded and not file2_excluded:
                filtered_pairs.append(pair)
            else:
                excluded_count += 1


        if excluded_count > 0:
            self.log_text.append(f"📊 Исключено пар из чёрного списка: {excluded_count}")

        return filtered_pairs

    def is_file_excluded(self, file_path):
        """Проверяет находится ли файл в исключённой папке"""
        if not hasattr(self, 'excluded_folders') or not self.excluded_folders:
            return False

        file_path = os.path.normpath(file_path)

        for excluded_folder in self.excluded_folders:
            excluded_folder = os.path.normpath(excluded_folder)
            if file_path.startswith(excluded_folder + os.sep):
                return True

        return False

    def create_pair_buttons(self, pairs: list):
        """Создает виджеты для пар с защитой от переполнения"""
        try:

            print(f"DEBUG: create_pair_buttons начат, пар: {len(pairs)}")

            # Проверяем, что методы существуют
            if not hasattr(self, 'create_file_widget'):
                print("ОШИБКА: метод create_file_widget не найден!")
                return

            # Очищаем предыдущие кнопки ПЕРЕД любыми другими операциями
            self.clear_pair_buttons()
            self.pair_widgets.clear()

            # Сбрасываем marked_for_deletion ПЕРЕД созданием новых виджетов
            self.marked_for_deletion.clear()

            # Ограничиваем количество одновременно отображаемых пар для тестирования
            display_pairs = pairs  # Убрал ограничение, используем все пары

            for i, (video1, video2, similarity, details) in enumerate(display_pairs, 1):
                # Проверяем существование файлов перед созданием виджетов
                if not os.path.exists(video1) or not os.path.exists(video2):
                    continue

                self.create_single_pair_widget(i, video1, video2, similarity, details)

            # Добавляем растягивающийся элемент
            self.pairs_layout.addStretch()

            # Обновляем UI удаления ПОСЛЕ создания всех виджетов
            self.update_deletion_ui()

            print(f"DEBUG: create_pair_buttons завершен, создано пар: {len(display_pairs)}")

        except Exception as e:
            print(f"Критическая ошибка в create_pair_buttons: {e}")
            import traceback
            traceback.print_exc()

    def create_single_pair_widget(self, index, video1, video2, similarity, details):
        """Создает виджет для одной пары (вынесено для упрощения)"""
        try:
            file1 = os.path.basename(video1)
            file2 = os.path.basename(video2)

            # Получаем размеры файлов
            size1 = os.path.getsize(video1) / (1024 * 1024) if os.path.exists(video1) else 0
            size2 = os.path.getsize(video2) / (1024 * 1024) if os.path.exists(video2) else 0

            # Создаем основной виджет пары
            pair_widget = QWidget()
            pair_layout = QVBoxLayout()
            pair_widget.setLayout(pair_layout)
            pair_widget.setStyleSheet("""
                QWidget {
                    background-color: #f8f9fa;
                    border: 1px solid #dee2e6;
                    border-radius: 5px;
                    margin: 3px;
                    padding: 5px;
                }
            """)

            # Верхняя строка: заголовок пары
            header_layout = QHBoxLayout()
            pair_title = QLabel(f"🎯 Пара {index}: {similarity:.1%} схожести")
            pair_title.setStyleSheet("font-weight: bold; font-size: 10pt; color: #2c3e50;")
            header_layout.addWidget(pair_title)
            header_layout.addStretch()

            # Кнопка сравнения
            compare_btn = QPushButton("🔍 Сравнить")
            compare_btn.clicked.connect(lambda checked, v1=video1, v2=video2: self.open_comparison_dialog([v1, v2]))
            compare_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 3px;
                    font-weight: bold;
                    font-size: 9pt;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            compare_btn.setMaximumWidth(100)
            header_layout.addWidget(compare_btn)
            pair_layout.addLayout(header_layout)

            # Нижняя строка: файлы с чекбоксами
            files_layout = QHBoxLayout()

            # Файл 1 - ВЫЗОВ БЕЗ INDEX
            file1_widget = self.create_file_widget(video1, file1, size1)
            files_layout.addWidget(file1_widget)

            # Разделитель
            separator = QLabel("🔄")
            separator.setStyleSheet("font-size: 14pt; margin: 0 5px;")
            separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            separator.setMaximumWidth(30)
            files_layout.addWidget(separator)

            # Файл 2 - ВЫЗОВ БЕЗ INDEX
            file2_widget = self.create_file_widget(video2, file2, size2)
            files_layout.addWidget(file2_widget)

            pair_layout.addLayout(files_layout)
            self.pairs_layout.addWidget(pair_widget)

        except Exception as e:
            print(f"Ошибка при создании виджета пары {index}: {e}")

    def create_file_widget(self, video_path, filename, size_mb):
        """Создает виджет для отображения файла с чекбоксом удаления БЕЗ index"""
        try:
            file_widget = QWidget()
            file_layout = QVBoxLayout()
            file_widget.setLayout(file_layout)
            file_widget.setMaximumWidth(220)

            # Создаем подробную информацию для tooltip
            full_tooltip = self.get_full_file_info(video_path, filename, size_mb)

            # Устанавливаем tooltip для всего виджета
            file_widget.setToolTip(full_tooltip)

            # Чекбокс удаления
            delete_container = QHBoxLayout()

            checkbox = QCheckBox("🗑️ УДАЛИТЬ")
            checkbox.setStyleSheet("""
                QCheckBox {
                    font-weight: bold;
                    color: #e74c3c;
                    spacing: 5px;
                    font-size: 9pt;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                }
                QCheckBox::indicator:unchecked {
                    border: 2px solid #bdc3c7;
                    background-color: white;
                    border-radius: 3px;
                }
                QCheckBox::indicator:checked {
                    border: 2px solid #e74c3c;
                    background-color: #e74c3c;
                    border-radius: 3px;
                }
            """)
            checkbox.toggled.connect(lambda checked, path=video_path: self.toggle_mark_deletion(path, checked))
            checkbox.setToolTip(f"Отметить файл для удаления\n\n{full_tooltip}")

            delete_container.addWidget(checkbox)
            delete_container.addStretch()

            file_layout.addLayout(delete_container)

            # Информация о файле
            info_text = QTextEdit()
            info_text.setFixedHeight(70)
            info_text.setMaximumWidth(210)
            info_text.setReadOnly(True)
            info_text.setStyleSheet("""
                QTextEdit {
                    background-color: white;
                    border: 1px solid #bdc3c7;
                    border-radius: 3px;
                    padding: 3px;
                    font-size: 8pt;
                    line-height: 1.2;
                }
            """)
            info_text.setToolTip(full_tooltip)

            # Компактная информация о файле С FPS
            file_info = self.get_compact_file_info(video_path, filename, size_mb)
            info_text.setPlainText(file_info)

            file_layout.addWidget(info_text)

            # Сохраняем ссылку на чекбокс
            # храним список чекбоксов для одного пути (чтобы поддержать дубликаты)
            self.pair_widgets.setdefault(video_path, []).append(checkbox)

            return file_widget

        except Exception as e:
            print(f"Ошибка при создании виджета файла {filename}: {e}")
            # Возвращаем простой виджет в случае ошибки
            error_widget = QLabel(f"Ошибка: {filename}")
            return error_widget

    def get_full_file_info(self, video_path, filename, size_mb):
        """Возвращает ПОЛНУЮ информацию о файле для tooltip"""

        def get_info():
            from src.core.frame_extractor import FrameExtractor
            extractor = FrameExtractor()
            video_info = extractor.get_video_info(video_path)

            info = f"📁 Полное имя: {filename}\n"
            info += f"📂 Путь: {video_path}\n"
            info += f"📏 Размер: {size_mb:.1f} MB\n"

            if video_info:
                duration = video_info.get('duration', 0)
                width = video_info.get('width', 0)
                height = video_info.get('height', 0)
                fps = video_info.get('fps', 0)
                total_frames = video_info.get('total_frames', 0)

                info += f"⏱️ Длительность: {duration:.1f} сек\n"
                info += f"🎞️ Разрешение: {width}x{height}\n"
                info += f"📊 FPS: {fps:.1f}\n"
                info += f"🖼️ Всего кадров: {total_frames}"
            else:
                info += "⚠️ Метаданные недоступны"

            return info

        return self.safe_file_operation(lambda x: get_info(), video_path,
                                        f"📁 {filename}\n📂 {video_path}\n📏 {size_mb:.1f} MB\n⚠️ Ошибка загрузки информации")

    def get_compact_file_info(self, video_path, filename, size_mb):
        """Возвращает КОМПАКТНУЮ форматированную информацию о файле С FPS"""
        try:
            from src.core.frame_extractor import FrameExtractor
            extractor = FrameExtractor()
            video_info = extractor.get_video_info(video_path)

            # Сокращаем имя файла если слишком длинное
            if len(filename) > 20:
                display_name = filename[:17] + "..."
            else:
                display_name = filename

            info = f"📁 {display_name}\n"
            info += f"📏 {size_mb:.1f}MB "

            if video_info:
                duration = video_info.get('duration', 0)
                width = video_info.get('width', 0)
                height = video_info.get('height', 0)
                fps = video_info.get('fps', 0)

                # Еще более компактное отображение
                if width > 0 and height > 0:
                    info += f"⏱️{duration:.0f}s\n"
                    # Используем сокращения для экономии места
                    info += f"📺{width}x{height} "
                    info += f"🎯{fps:.0f}fps"
                else:
                    info += f"\n⏱️{duration:.0f}s {fps:.0f}fps"
            else:
                info += "\n⚠️ Нет метаданных"

            return info
        except Exception as e:
            return f"📁 {filename[:20]}\n📏 {size_mb:.1f}MB\n⚠️ Ошибка"

    def toggle_mark_deletion(self, file_path: str, marked: bool):
        """Ведём счётчик сколько чекбоксов отмечено для файла"""
        if not hasattr(self, 'file_reference_count'):
            self.file_reference_count = {}

        if marked:
            self.file_reference_count[file_path] = self.file_reference_count.get(file_path, 0) + 1
        else:
            self.file_reference_count[file_path] = self.file_reference_count.get(file_path, 1) - 1

        # Файл отмечен если есть ХОТЯ БЫ ОДНА отметка
        if self.file_reference_count.get(file_path, 0) > 0:
            self.marked_for_deletion.add(file_path)
        else:
            self.marked_for_deletion.discard(file_path)

        self.update_deletion_ui()

    def update_deletion_ui(self):
        """Обновляет UI управления удалением с подсчетом размера"""
        try:
            count = len(self.marked_for_deletion)

            # Подсчитываем общий размер отмеченных файлов
            total_size = 0
            for file_path in self.marked_for_deletion:
                try:
                    if os.path.exists(file_path):  # Проверяем существование файла
                        total_size += os.path.getsize(file_path)
                except OSError:
                    # Файл мог быть удален или недоступен
                    continue

            total_size_mb = total_size / (1024 * 1024)

            self.marked_count_label.setText(f"📊 Отмечено: {count} файлов")
            self.total_size_label.setText(f"💾 Размер: {total_size_mb:.1f} MB")
            self.delete_marked_btn.setEnabled(count > 0)

            # Обновляем текст кнопки в зависимости от количества
            if count > 0:
                self.delete_marked_btn.setText(f"🗑️ УДАЛИТЬ ({count})")
            else:
                self.delete_marked_btn.setText("🗑️ УДАЛИТЬ")

        except Exception as e:
            print(f"Ошибка при обновлении UI удаления: {e}")

    def delete_marked_files(self):
        """Удаляет все отмеченные файлы с улучшенной защитой"""
        try:
            print("DEBUG: delete_marked_files начат")

            if not self.marked_for_deletion:
                print("DEBUG: Нет файлов для удаления")
                return

            # Создаем копию для безопасной итерации
            files_to_delete = list(self.marked_for_deletion)
            valid_files = [f for f in files_to_delete if os.path.exists(f)]

            if not valid_files:
                QMessageBox.warning(self, "Внимание", "Нет действительных файлов для удаления")
                return

            # Диалог подтверждения
            reply = QMessageBox.question(
                self,
                "📋 Подтверждение удаления",
                f"Вы уверены, что хотите удалить {len(valid_files)} файлов?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # Удаляем файлы БЕЗ прогресс-диалога (упрощаем)
            deleted_count = 0
            errors = []

            for file_path in valid_files:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    self.marked_for_deletion.discard(file_path)
                except Exception as e:
                    errors.append(f"{os.path.basename(file_path)}: {str(e)}")

            # Обновляем пары - упрощенная версия
            if hasattr(self, 'current_pairs'):
                self.current_pairs = [
                    pair for pair in self.current_pairs
                    if os.path.exists(pair[0]) and os.path.exists(pair[1])
                ]

            # Обновляем UI
            self.update_deletion_ui()

            # ПЕРЕСОЗДАЕМ ВИДЖЕТЫ ТОЛЬКО ЕСЛИ ЕСТЬ ИЗМЕНЕНИЯ
            if deleted_count > 0 and hasattr(self, 'current_pairs'):
                self.create_pair_buttons(self.current_pairs)

            # Централизованно обновляем доступность кнопок сравнения/просмотра
            self.update_compare_controls()

            # Показываем результаты
            result_msg = f"✅ Удалено {deleted_count} файлов"
            if errors:
                result_msg += f"\n❌ Ошибки: {len(errors)}"
                QMessageBox.warning(self, "Результат", result_msg)
            else:
                QMessageBox.information(self, "Успех", result_msg)

            self.log_text.append(f"🗑️ Удалено {deleted_count} файлов")
            print("DEBUG: delete_marked_files завершен")

        except Exception as e:
            error_msg = f"Критическая ошибка при удалении: {str(e)}"
            print(error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)
            import traceback
            traceback.print_exc()

    def safe_file_operation(self, operation, file_path, default=None):
        """Безопасное выполнение операций с файлами"""
        try:
            if os.path.exists(file_path):
                return operation(file_path)
            else:
                return default
        except Exception as e:
            print(f"Ошибка при операции с файлом {file_path}: {e}")
            return default

    def create_group_buttons(self, groups):
        """Создает кнопки для групп с улучшенной информацией"""
        for i, group in enumerate(groups, 1):
            # Создаем информационную строку для группы
            group_info = f"Группа {i} ({len(group)} видео)"

            # Добавляем информацию о размерах файлов
            total_size = sum(os.path.getsize(video) for video in group) / (1024 * 1024)  # MB
            avg_size = total_size / len(group) if group else 0

            group_btn = QPushButton(f"🎬 {group_info}\n"
                                    f"📏 Файлов: {len(group)}, Средний размер: {avg_size:.1f} MB")
            group_btn.clicked.connect(lambda checked, idx=i - 1: self.open_group_management(idx))
            group_btn.setStyleSheet("QPushButton { text-align: left; padding: 8px; }")
            self.groups_layout.addWidget(group_btn)

    def on_video_deleted(self, video_path):
        """Обрабатывает удаление файла — нормализует пути, очищает пометки и селекции для сравнения."""
        try:
            norm_path = self.normalize_path(video_path)
            norm_case = os.path.normcase(norm_path)

            # Убираем из marked_for_deletion
            to_remove = {p for p in self.marked_for_deletion if os.path.normcase(self.normalize_path(p)) == norm_case}
            for p in to_remove:
                self.marked_for_deletion.discard(p)

            # Обновляем current_pairs — исключаем пары с удалённым файлом
            new_pairs = []
            for pair in getattr(self, 'current_pairs', []):
                try:
                    a = os.path.normcase(self.normalize_path(pair[0]))
                    b = os.path.normcase(self.normalize_path(pair[1]))
                except Exception:
                    continue
                if a != norm_case and b != norm_case:
                    new_pairs.append(pair)
            self.current_pairs = new_pairs

            # Очистим селекции в табе сравнения, если удалённый файл там выбран
            try:
                if hasattr(self, 'video1_path') and self.video1_path:
                    if os.path.normcase(self.normalize_path(self.video1_path)) == norm_case:
                        self.video1_path = ""
                        if hasattr(self, 'video1_label'):
                            self.video1_label.setText("Видео не выбрано")
                        if hasattr(self, 'delete_video1_btn'):
                            self.delete_video1_btn.setEnabled(False)

                if hasattr(self, 'video2_path') and self.video2_path:
                    if os.path.normcase(self.normalize_path(self.video2_path)) == norm_case:
                        self.video2_path = ""
                        if hasattr(self, 'video2_label'):
                            self.video2_label.setText("Видео не выбрано")
                        if hasattr(self, 'delete_video2_btn'):
                            self.delete_video2_btn.setEnabled(False)
            except Exception as e:
                print("Ошибка при сбросе селекций сравнения:", e)

            # Обновляем кнопку просмотра пары
            if hasattr(self, 'view_pair_btn'):
                self.view_pair_btn.setEnabled(bool(self.video1_path and self.video2_path))

            if hasattr(self, 'compare_btn'):
                self.compare_btn.setEnabled(bool(self.video1_path and self.video2_path))

            # Обновляем UI удаления и заносим запись в лог
            self.update_deletion_ui()
            self.create_pair_buttons(self.current_pairs)
            try:
                if hasattr(self, 'compare_results') and self.compare_results:
                    self.compare_results.append(f"\n🗑️ Файл удалён: {os.path.basename(norm_path)}")
            except Exception:
                pass

            self.log_text.append(f"🗑️ Файл удалён: {os.path.basename(norm_path)}")

        except Exception as e:
            print(f"Ошибка в on_video_deleted: {e}")

    def open_comparison_dialog(self, video_paths):
        """Открывает side-by-side сравнение для выбранной пары"""
        if len(video_paths) < 2:
            self.show_warning("Для сравнения нужно как минимум 2 видеофайла!")
            return

        try:
            from src.gui.comparison_dialog import ComparisonDialog
            # Нормализуем пути перед передачей в диалог
            norm_paths = [self.normalize_path(p) for p in video_paths[:2]]
            dialog = ComparisonDialog(norm_paths, self)

            # Подключаем сигнал запроса удаления: MainWindow выполнит безопасное удаление
            dialog.file_delete_requested.connect(lambda p, dlg=dialog: self._handle_dialog_delete_request(p, dlg))

            # Подключаем сигнал, который диалог ожидает получить после удаления (совместимость)
            # Но MainWindow также хочет знать о том, что файл удалён => подпишемся на dialog.file_deleted,
            # чтобы обновить marked_for_deletion и current_pairs если диалог сам эмиттит этот сигнал.
            dialog.file_deleted.connect(self.on_video_deleted)

            dialog.exec()
        except Exception as e:
            print(f"Ошибка при открытии ComparisonDialog: {e}")
            # Fallback на упрощенный диалог
            try:
                from src.gui.simple_comparison_dialog import SimpleComparisonDialog
                self.log_text.append("⚠️ Используем упрощенный режим сравнения")
                dialog = SimpleComparisonDialog(video_paths, self)
                dialog.exec()
            except Exception as e2:
                print(f"Ошибка при открытии SimpleComparisonDialog: {e2}")

    def show_pair_info(self, video_paths):
        """Показывает информацию о паре если диалоги не работают"""
        info = "🎬 ИНФОРМАЦИЯ О ПАРЕ:\n\n"
        for i, path in enumerate(video_paths[:2]):
            if os.path.exists(path):
                size = os.path.getsize(path) / (1024 * 1024)
                info += f"Видео {i + 1}:\n"
                info += f"📁 Файл: {os.path.basename(path)}\n"
                info += f"📏 Размер: {size:.1f} MB\n"
                info += f"📂 Путь: {path}\n\n"
            else:
                info += f"Видео {i + 1}: ФАЙЛ НЕ НАЙДЕН - {path}\n\n"

        self.log_text.append(info)

    def clear_pair_buttons(self):
        """Очищает кнопки пар с защитой от рекурсии"""
        try:
            if not hasattr(self, 'pairs_layout') or not self.pairs_layout:
                return

            # Отключаем сигналы чтобы избежать рекурсивных вызовов
            for cb_list in self.pair_widgets.values():
                if not cb_list:
                    continue
                # cb_list гарантированно список
                for checkbox in cb_list:
                    if checkbox:
                        try:
                            checkbox.toggled.disconnect()
                        except Exception:
                            pass

            # Очищаем layout
            while self.pairs_layout.count():
                item = self.pairs_layout.takeAt(0)
                if item.widget():
                    widget = item.widget()
                    widget.setParent(None)
                    widget.deleteLater()

            self.pair_widgets.clear()
            print("DEBUG: clear_pair_buttons завершен")

        except Exception as e:
            print(f"Ошибка в clear_pair_buttons: {e}")

    def show_simple_comparison(self, video_paths):
        """Показывает простое сравнение в основном окне как запасной вариант"""
        info = "🔍 СРАВНЕНИЕ ВИДЕО (основное окно):\n\n"

        for i, path in enumerate(video_paths[:2]):
            if os.path.exists(path):
                size = os.path.getsize(path) / (1024 * 1024)
                info += f"Видео {i + 1}: {os.path.basename(path)}\n"
                info += f"   Размер: {size:.1f} MB\n"
                info += f"   Путь: {path}\n\n"
            else:
                info += f"Видео {i + 1}: ФАЙЛ НЕ НАЙДЕН - {path}\n\n"

        info += "⚠️ Для детального сравнения проверьте наличие файлов:\n"
        info += "   - comparison_dialog.py\n"
        info += "   - simple_comparison_dialog.py\n"
        info += "   в папке src/gui/"

        self.log_text.append(info)

    def scan_thread_finished(self):
        """Вызывается когда поток сканирования завершил работу"""
        self.set_scan_ui_enabled(True)
        self.progress_bar.setVisible(False)

    # =============================================================================
    # МЕТОДЫ ДЛЯ ВКЛАДКИ СРАВНЕНИЯ
    # =============================================================================

    def select_video_for_comparison(self, video_num: int):
        """Выбирает видеофайл для сравнения и обновляет кнопки управления"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Выберите видео файл #{video_num}",
            "",
            f"Video Files ({' '.join(['*' + fmt for fmt in Config.SUPPORTED_FORMATS])})"
        )
        if file_path:
            if video_num == 1:
                self.video1_path = file_path
                self.video1_label.setText(f"Выбрано: {os.path.basename(file_path)}")
            else:
                self.video2_path = file_path
                self.video2_label.setText(f"Выбрано: {os.path.basename(file_path)}")

        # Включаем/выключаем элементы управления в одной точке
        self.update_compare_controls()

    def compare_selected_videos(self):
        """Сравнивает два выбранных видеофайла"""
        if not self.video1_path or not self.video2_path:
            self.show_warning("Выберите оба видеофайла для сравнения!")
            return

        self.compare_results.clear()
        self.compare_results.setPlainText("🔄 Начинаем сравнение...")

        # Берём число кадров из SpinBox (по умолчанию 10)
        max_frames = self.frame_count_spin.value() if hasattr(self, 'frame_count_spin') else 10

        # Запускаем сравнение в отдельном потоке, передавая max_frames
        mapping = {0: 'simple', 1: 'phash', 2: 'cnn_faiss'}
        idx = self.compare_algorithm_combo.currentIndex()
        alg_name = mapping.get(idx, 'simple')
        comparator = self.create_algorithm_instance_from_ui(alg_name, context='compare')

        # затем
        self.compare_thread = CompareThread(comparator, self.video1_path, self.video2_path, max_frames=max_frames)
        self.compare_thread.result_signal.connect(self.show_comparison_result)
        self.compare_thread.start()

    def show_comparison_result(self, result: dict):
        """Показывает результаты сравнения двух видео"""
        self.compare_results.append("\n📊 РЕЗУЛЬТАТЫ СРАВНЕНИЯ:")
        self.compare_results.append(f"🎯 Общая схожесть: {result['similarity']:.2%}")

        if 'error' in result:
            self.compare_results.append(f"❌ Ошибка: {result['error']}")
            return

        # Показываем детали по каждому сравнению кадров
        for i, comparison in enumerate(result['frame_comparisons'], 1):
            self.compare_results.append(f"\n🔍 Сравнение кадров #{i}:")
            self.compare_results.append(f"   Общая схожесть: {comparison['similarity']:.2%}")

            # Детали по каждому алгоритму
            for algo_name, algo_score in comparison['algorithm_details'].items():
                if algo_name != 'overall':
                    self.compare_results.append(f"   - {algo_name}: {algo_score:.2%}")

        if 'error' in result:
            self.compare_results.append(f"\n❌ Ошибка: {result['error']}")
        else:
            self.compare_results.append("\n✅ Сравнение завершено")

    # =============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =============================================================================

    def set_scan_ui_enabled(self, enabled: bool):
        """Включает/выключает элементы UI во время сканирования"""
        self.scan_button.setEnabled(enabled)
        self.select_button.setEnabled(enabled)
        self.similarity_threshold_input.setEnabled(enabled)

    def show_warning(self, message: str):
        """Показывает предупреждающее сообщение"""
        QMessageBox.warning(self, "Внимание", message)

    def update_compare_controls(self):
        """
        Централизованно обновляет доступность кнопок просмотра/сравнения
        на вкладке сравнения в зависимости от текущих selection (и существования файлов).
        """
        try:
            # Проверяем, есть ли выбранные пути и существуют ли файлы на диске
            def is_valid(path):
                if not path:
                    return False
                try:
                    return os.path.exists(self.normalize_path(path))
                except Exception:
                    return os.path.exists(path)

            valid1 = is_valid(getattr(self, 'video1_path', None))
            valid2 = is_valid(getattr(self, 'video2_path', None))
            both_selected = bool(valid1 and valid2)

            # view_pair_btn — кнопка для просмотра пары (если есть)
            if hasattr(self, 'view_pair_btn'):
                try:
                    self.view_pair_btn.setEnabled(both_selected)
                except Exception:
                    pass

            # compare_btn — кнопка для запуска сравнения
            if hasattr(self, 'compare_btn'):
                try:
                    self.compare_btn.setEnabled(both_selected)
                except Exception:
                    pass

            # delete buttons beside each selected video
            if hasattr(self, 'delete_video1_btn'):
                try:
                    self.delete_video1_btn.setEnabled(valid1)
                except Exception:
                    pass
            if hasattr(self, 'delete_video2_btn'):
                try:
                    self.delete_video2_btn.setEnabled(valid2)
                except Exception:
                    pass

        except Exception as e:
            print(f"Ошибка в update_compare_controls: {e}")

    def delete_video_file(self, video_num: int):
        """Удаляет выбранный файл прямо из вкладки сравнения (с подтверждением)."""
        raw_path = self.video1_path if video_num == 1 else self.video2_path
        if not raw_path:
            self.show_warning("Файл не выбран")
            return

        # Нормализуем путь перед работой с файловой системой
        path = self.normalize_path(raw_path)

        # Если файл не найден — сообщаем и очищаем селекцию
        if not os.path.exists(path):
            self.show_warning(f"Файл не найден на диске:\n{path}")
            if video_num == 1:
                self.video1_path = ""
                self.video1_label.setText("Видео не выбрано")
                if hasattr(self, 'delete_video1_btn'):
                    self.delete_video1_btn.setEnabled(False)
            else:
                self.video2_path = ""
                self.video2_label.setText("Видео не выбрано")
                if hasattr(self, 'delete_video2_btn'):
                    self.delete_video2_btn.setEnabled(False)
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить файл:\n{os.path.basename(path)} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            os.remove(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка при удалении", f"Не удалось удалить файл: {e}")
            return

        # Обновляем поля UI после успешного удаления
        if video_num == 1:
            self.video1_path = ""
            self.video1_label.setText("Видео не выбрано")
            if hasattr(self, 'delete_video1_btn'):
                self.delete_video1_btn.setEnabled(False)
        else:
            self.video2_path = ""
            self.video2_label.setText("Видео не выбрано")
            if hasattr(self, 'delete_video2_btn'):
                self.delete_video2_btn.setEnabled(False)

        if hasattr(self, 'view_pair_btn'):
            self.view_pair_btn.setEnabled(False)

        # Централизованно обновляем доступность кнопок сравнения/просмотра
        self.update_compare_controls()

        # Сообщаем остальным подсистемам о том, что файл удалён
        try:
            self.on_video_deleted(path)
        except Exception:
            pass

        self.log_text.append(f"🗑️ Удалено: {os.path.basename(path)}")

    def _handle_dialog_delete_request(self, raw_path: str, dialog):
        """
        Обрабатывает запрос диагонога на удаление файла.
        Делает безопасную нормализацию и удаление, обновляет UI и уведомляет диалог.
        """
        try:
            path = self.normalize_path(raw_path)

            # Попробуем безопасно удалить: сначала send2trash, потом os.remove
            deleted = False
            last_err = ""
            try:
                import send2trash
                try:
                    send2trash.send2trash(path)
                    deleted = True
                except Exception as e:
                    last_err = str(e)
            except Exception:
                # send2trash не доступен — пробуем os.remove
                try:
                    os.remove(path)
                    deleted = True
                except Exception as e:
                    last_err = str(e)

            # Если не удалили, попробуем fallback варианты (без префикса \\?\)
            if not deleted:
                # Пробуем убрать \\?\ если есть
                fallback = path[4:] if path.startswith("\\\\?\\") else path
                try:
                    if os.path.exists(fallback):
                        os.remove(fallback)
                        deleted = True
                except Exception as e:
                    last_err = str(e)

            if not deleted:
                # Ещё вариант — один последний кандидат: нормализованный
                try:
                    norm = os.path.normpath(path)
                    if os.path.exists(norm):
                        os.remove(norm)
                        deleted = True
                except Exception as e:
                    last_err = str(e)

            if not deleted:
                # Сообщаем пользователю об ошибке
                QMessageBox.critical(self, "Ошибка при удалении", f"Не удалось удалить файл: {last_err}")
                return

            # Успешное удаление — обновляем внутренние структуры
            self.on_video_deleted(path)

            try:
                # уведомляем диалог что файл удалён (диалог обновит UI)
                dialog.file_deleted.emit(path)
            except Exception:
                pass

                # Закрываем диалог — безопасно
            try:
                # если в диалоге есть метод safe_close — используем его (останавливает потоки)
                if hasattr(dialog, 'safe_close'):
                    dialog.safe_close()
                # если диалог modal exec() — закрываем
                try:
                    dialog.accept()
                except Exception:
                    dialog.close()
            except Exception as e:
                print("Ошибка при закрытии диалога после удаления:", e)

                # Лог и возврат
            self.log_text.append(f"🗑️ Удалено (из диалога): {os.path.basename(path)}")
            return

        except Exception as e:
            print(f"Ошибка при обработке запроса удаления из диалога: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл: {e}")

    def normalize_path(self, path: str) -> str:
        """
        Нормализует путь:
          - обрабатывает file:// URL,
          - убирает префикс Windows long path '\\\\?\\',
          - приводит к нормальному абсолютному пути.
        """
        try:
            if not path:
                return path

            # Если пришёл file:// URL (например file:///D:/...), попробуем получить локальный путь
            if isinstance(path, str) and path.startswith("file://"):
                q = QUrl(path)
                local = q.toLocalFile()
                if local:
                    path = local

            # Убираем префикс Windows long path '\\\\?\\' (если он присутствует)
            # В runtime-строке префикс выглядит как '\\\\?\\', проверяем именно такую строку.
            if path.startswith("\\\\?\\"):
                path = path[4:]

            # Нормализуем слэши и путь
            # Сначала заменим явные '/' на os.sep (на случай смешанных слэшей)
            path = path.replace("/", os.sep)
            # Затем приведём к нормальной форме и абсолютному пути
            path = os.path.normpath(path)
            path = os.path.abspath(path)

            return path
        except Exception as e:
            # Логируем, но возвращаем исходный путь, чтобы не ломать логику
            print(f"Ошибка в normalize_path: {e}")
            return path

    def refresh_file_list(self):
        """Обновляет список файлов (например, после удаления)"""
        self.log_text.append("\n🔄 Список файлов обновлен")

    def closeEvent(self, event):
        """Обрабатывает закрытие приложения с улучшенной очисткой"""
        try:
            print("DEBUG: Завершение приложения...")

            # Останавливаем потоки если они работают
            if hasattr(self,
                       'optimized_scan_thread') and self.optimized_scan_thread and self.optimized_scan_thread.isRunning():
                self.optimized_scan_thread.terminate()
                self.optimized_scan_thread.wait(1000)  # Ждем 1 секунду

            if hasattr(self, 'compare_thread') and self.compare_thread and self.compare_thread.isRunning():
                self.compare_thread.terminate()
                self.compare_thread.wait(1000)

            # Очищаем виджеты
            if hasattr(self, 'pairs_layout') and self.pairs_layout:
                self.clear_pair_buttons()

            print("DEBUG: Приложение завершено корректно")
            event.accept()

        except Exception as e:
            print(f"Ошибка при завершении приложения: {e}")
            event.accept()  # Все равно принимаем закрытие

    def on_algorithm_changed(self, index):
        """Обработчик смены алгоритма в UI (синхронизируем оба combobox'а)"""
        mapping = {
            0: 'simple',
            1: 'phash',
            2: 'cnn_faiss'
        }
        name = mapping.get(index, 'simple')

        # синхронизировать второй combobox без рекурсии
        try:
            if hasattr(self, 'compare_algorithm_combo'):
                # если index отличается — заблокировать сигнал и установить
                if self.compare_algorithm_combo.currentIndex() != index:
                    self.compare_algorithm_combo.blockSignals(True)
                    self.compare_algorithm_combo.setCurrentIndex(index)
                    self.compare_algorithm_combo.blockSignals(False)
            if hasattr(self, 'algorithm_combo'):
                if self.algorithm_combo.currentIndex() != index:
                    self.algorithm_combo.blockSignals(True)
                    self.algorithm_combo.setCurrentIndex(index)
                    self.algorithm_combo.blockSignals(False)
        except Exception:
            pass

        # Установим comparator с учётом параметров pHash (если применимо)
        self.set_comparator_from_selection(name)

    def on_scan_algorithm_changed(self, index):
        mapping = {0: 'simple', 1: 'phash', 2: 'cnn_faiss'}
        name = mapping.get(index, 'simple')
        is_phash = (name == 'phash')

        # показываем/скрываем элементы pHash на вкладке Scan
        try:
            if hasattr(self, 'phash_frames_label'):
                self.phash_frames_label.setVisible(is_phash)
            if hasattr(self, 'phash_frames_spin'):
                self.phash_frames_spin.setVisible(is_phash)

            if hasattr(self, 'phash_ham_label'):
                self.phash_ham_label.setVisible(is_phash)
            if hasattr(self, 'phash_ham_spin'):
                self.phash_ham_spin.setVisible(is_phash)
        except Exception as e:
            print("on_scan_algorithm_changed error:", e)

    def on_compare_algorithm_changed(self, index):
        mapping = {0: 'simple', 1: 'phash', 2: 'cnn_faiss'}
        name = mapping.get(index, 'simple')
        is_phash = (name == 'phash')

        # показываем/скрываем элементы pHash на вкладке Compare
        try:
            if hasattr(self, 'compare_phash_frames_label'):
                self.compare_phash_frames_label.setVisible(is_phash)
            if hasattr(self, 'compare_phash_frames_spin'):
                self.compare_phash_frames_spin.setVisible(is_phash)

            if hasattr(self, 'compare_phash_ham_label'):
                self.compare_phash_ham_label.setVisible(is_phash)
            if hasattr(self, 'compare_phash_ham_spin'):
                self.compare_phash_ham_spin.setVisible(is_phash)
        except Exception as e:
            print("on_compare_algorithm_changed error:", e)

    def set_comparator_from_selection(self, name: str):
        """
        Создаёт comparator через фабрику и при необходимости уведомляет пользователя,
        если выбранный алгоритм ещё не реализован — в этом случае будет использован simple.
        Также передаёт параметры pHash, если они есть в UI.
        """
        alg = create_algorithm(name)
        # Если phash доступен, попробуем установить кастомные параметры
        try:
            if name == 'phash':
                # берем значения из UI, если они есть
                frames_val = getattr(self, 'phash_frames_spin', None)
                ham_val = getattr(self, 'phash_ham_spin', None)
                if frames_val is not None and ham_val is not None:
                    try:
                        # если объект поддерживает поля, установим их
                        if hasattr(alg, 'frames_to_sample'):
                            alg.frames_to_sample = int(self.phash_frames_spin.value())
                        if hasattr(alg, 'ham_thresh'):
                            alg.ham_thresh = int(self.phash_ham_spin.value())
                    except Exception:
                        pass
        except Exception:
            pass

        if not getattr(alg, 'implemented', True):
            QMessageBox.information(
                self,
                "Алгоритм временно недоступен",
                f"Алгоритм '{name}' пока не реализован в этой ветке.\n"
                "Будет использован режим 'Simple (original)'."
            )
            alg = create_algorithm('simple')
            self.current_algorithm_name = 'simple'
        else:
            self.current_algorithm_name = name

        self.comparator = alg

# =============================================================================
# ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ
# =============================================================================

def load_license_text():
    """Загружает текст лицензии из файла"""
    try:
        # Пробуем разные пути
        possible_paths = [
            resource_path("static/license.txt"),
            os.path.join("static", "license.txt"),
            os.path.join(os.path.dirname(__file__), "static", "license.txt"),
        ]

        for license_path in possible_paths:
            if os.path.exists(license_path):
                with open(license_path, 'r', encoding='utf-8') as f:
                    return f.read()

        # Fallback: если файл не найден
        return """
        ЛИЦЕНЗИОННОЕ СОГЛАШЕНИЕ

        [Файл license.txt не найден]

        Программа предоставляется "как есть".
        """

    except Exception as e:
        return f"Ошибка загрузки лицензии: {e}"


def check_license() -> bool:
    """Проверяет принятие лицензии, возвращает True если принята"""
    config_file = "user_settings.json"

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                settings = json.load(f)
                if settings.get('license_accepted', False):
                    return True
        except:
            pass

    # Загружаем лицензию из файла
    license_content = load_license_text()

    # Создаем кастомное диалоговое окно
    dialog = QDialog()
    dialog.setWindowTitle("VideoDuplicate Cleaner - Лицензионное соглашение")
    dialog.setGeometry(100, 100, 600, 400)

    layout = QVBoxLayout(dialog)

    # Заголовок
    title_label = QLabel("Пожалуйста, ознакомьтесь с лицензионным соглашением:")
    title_label.setStyleSheet("font-weight: bold; font-size: 12pt; margin: 10px;")
    layout.addWidget(title_label)

    # Поле с текстом лицензии (прокручиваемое)
    license_text = QTextEdit()  # ← СОЗДАЛИ ПЕРЕМЕННУЮ
    license_text.setReadOnly(True)
    license_text.setPlainText(license_content)
    layout.addWidget(license_text)

    # Кнопки
    button_layout = QHBoxLayout()

    accept_btn = QPushButton("✅ Принимаю")
    accept_btn.clicked.connect(lambda: dialog.accept())
    accept_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px; font-weight: bold;")

    reject_btn = QPushButton("❌ Не принимаю")
    reject_btn.clicked.connect(lambda: dialog.reject())
    reject_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px; font-weight: bold;")

    button_layout.addWidget(accept_btn)
    button_layout.addWidget(reject_btn)
    layout.addLayout(button_layout)

    # Показать окно по центру
    dialog.setModal(True)

    # Запускаем диалог
    if dialog.exec() == QDialog.DialogCode.Accepted:
        with open(config_file, 'w') as f:
            json.dump({'license_accepted': True}, f, indent=2)
        return True
    else:
        return False

def main():
    """Основная функция запуска приложения"""

    # Создаем временное приложение для диалога
    temp_app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()

    # Проверяем лицензию
    if not check_license():
        print("Лицензионное соглашение не принято. Программа завершена.")
        return  # Выходим без запуска GUI

    # Если дошли сюда - лицензия принята, запускаем основное окно

    # Создаем основное приложение (если нужно новое)
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()

    app.setApplicationName("VideoDuplicate Cleaner")
    app.setApplicationVersion("1.0")

    # Создаем и показываем главное окно
    window = MainWindow()
    window.show()

    # Запускаем цикл событий
    sys.exit(app.exec())

if __name__ == "__main__":
    main()