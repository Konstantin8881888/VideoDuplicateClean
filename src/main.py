import os
import sys
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QFileDialog, QTextEdit, QProgressBar, QTabWidget, QHBoxLayout,
    QLineEdit, QMessageBox, QScrollArea, QCheckBox, QFrame, QProgressDialog
)
from PyQt6.QtCore import QThread, pyqtSignal, QUrl, Qt
from PyQt6.QtGui import QFont

# импорты наших модулей
from src.core.file_scanner import FileScanner
from src.core.frame_extractor import FrameExtractor
from src.core.optimized_comparator import OptimizedVideoComparator
from src.config import Config


# =============================================================================
# КЛАССЫ ДЛЯ МНОГОПОТОЧНОСТИ
# =============================================================================

class OptimizedScanThread(QThread):
    """Поток для оптимизированного сканирования папки"""

    # Сигналы для обновления UI из потока
    progress_signal = pyqtSignal(int, str)  # прогресс (проценты, сообщение)
    result_signal = pyqtSignal(list)  # финальные результаты
    finished_signal = pyqtSignal()  # завершение работы

    def __init__(self, comparator, folder_path, similarity_threshold=None):
        super().__init__()
        self.comparator = comparator
        self.folder_path = folder_path
        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else Config.SIMILARITY_THRESHOLD
        self.scanner = FileScanner()

    def run(self):
        """Основной метод, который выполняется в потоке"""
        try:
            self.progress_signal.emit(0, "Поиск видеофайлов...")

            # Находим все видеофайлы
            video_files = self.scanner.find_video_files(self.folder_path)

            if not video_files:
                self.result_signal.emit([])
                return

            self.progress_signal.emit(10, f"Найдено {len(video_files)} видеофайлов")

            # Запускаем оптимизированный поиск похожих видео
            similar_pairs = self.comparator.find_similar_videos_optimized(
                video_files,
                self.similarity_threshold
            )

            # Отправляем результаты в основной поток
            self.result_signal.emit(similar_pairs)

        except Exception as e:
            print(f"Ошибка в потоке сканирования: {e}")
            import traceback
            traceback.print_exc()
            self.result_signal.emit([])
        finally:
            self.finished_signal.emit()


class CompareThread(QThread):
    """Поток для сравнения двух конкретных видеофайлов"""

    result_signal = pyqtSignal(dict)

    def __init__(self, comparator, video1_path, video2_path):
        super().__init__()
        self.comparator = comparator
        self.video1_path = video1_path
        self.video2_path = video2_path

    def run(self):
        result = self.comparator.compare_videos(self.video1_path, self.video2_path)
        self.result_signal.emit(result)


# =============================================================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VideoDuplicate Cleaner")
        self.setGeometry(100, 100, 1000, 800)  # Увеличили высоту окна

        # Инициализация компонентов
        self.scanner = FileScanner()
        self.frame_extractor = FrameExtractor()
        self.comparator = OptimizedVideoComparator()

        # Переменные состояния
        self.selected_folder = ""
        self.video1_path = ""
        self.video2_path = ""
        self.current_pairs = []
        self.optimized_scan_thread = None
        self.compare_thread = None
        self.marked_for_deletion = set()  # Файлы, отмеченные для удаления
        self.pair_widgets = {}  # Виджеты пар для управления чекбоксами

        # Атрибуты для управления кнопками пар
        self.pairs_container = None
        self.pairs_layout = None

        # Создаем интерфейс
        self.setup_ui()

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

    def create_scan_tab(self):
        """Создает вкладку для сканирования папки с прокруткой и управлением удалением"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Заголовок
        title_label = QLabel("Поиск похожих видеофайлов в папке")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title_label)

        # Выбор папки
        folder_layout = QHBoxLayout()
        self.select_button = QPushButton("Выбрать папку для сканирования")
        self.select_button.clicked.connect(self.select_folder)
        folder_layout.addWidget(self.select_button)

        self.selected_folder_label = QLabel("Папка не выбрана")
        folder_layout.addWidget(self.selected_folder_label)
        layout.addLayout(folder_layout)

        # Настройки сканирования
        settings_layout = QHBoxLayout()

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
        """Создает вкладку для сравнения двух видео"""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Заголовок
        title_label = QLabel("Сравнение двух видеофайлов")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title_label)

        # Выбор первого видео
        video1_layout = QHBoxLayout()
        self.select_video1_btn = QPushButton("Выбрать первое видео")
        self.select_video1_btn.clicked.connect(lambda: self.select_video_for_comparison(1))
        video1_layout.addWidget(self.select_video1_btn)

        self.video1_label = QLabel("Видео не выбрано")
        video1_layout.addWidget(self.video1_label)
        layout.addLayout(video1_layout)

        # Выбор второго видео
        video2_layout = QHBoxLayout()
        self.select_video2_btn = QPushButton("Выбрать второе видео")
        self.select_video2_btn.clicked.connect(lambda: self.select_video_for_comparison(2))
        video2_layout.addWidget(self.select_video2_btn)

        self.video2_label = QLabel("Видео не выбрано")
        video2_layout.addWidget(self.video2_label)
        layout.addLayout(video2_layout)

        # Кнопка сравнения
        self.compare_btn = QPushButton("🔍 Сравнить выбранные видео")
        self.compare_btn.clicked.connect(self.compare_selected_videos)
        layout.addWidget(self.compare_btn)

        # Результаты сравнения
        self.compare_results = QTextEdit()
        self.compare_results.setPlaceholderText("Результаты сравнения появятся здесь...")
        self.compare_results.setReadOnly(True)
        layout.addWidget(self.compare_results)

        return widget

    def update_deletion_ui(self):
        """Обновляет UI управления удалением БЕЗ рекурсивных вызовов"""
        try:
            if not hasattr(self, 'marked_count_label') or not self.marked_count_label:
                return

            count = len(self.marked_for_deletion)

            # Быстрый подсчет размера без глубокой рекурсии
            total_size = 0
            valid_files = []

            for file_path in list(self.marked_for_deletion):  # Используем list для копирования
                try:
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
                        valid_files.append(file_path)
                except (OSError, Exception):
                    continue

            # Обновляем множество
            self.marked_for_deletion = set(valid_files)
            count = len(self.marked_for_deletion)
            total_size_mb = total_size / (1024 * 1024) if total_size > 0 else 0

            # Безопасное обновление UI
            self.marked_count_label.setText(f"📊 Отмечено: {count} файлов")
            self.total_size_label.setText(f"💾 Размер: {total_size_mb:.1f} MB")

            if hasattr(self, 'delete_marked_btn'):
                self.delete_marked_btn.setEnabled(count > 0)
                self.delete_marked_btn.setText(f"🗑️ УДАЛИТЬ ({count})" if count > 0 else "🗑️ УДАЛИТЬ")

        except Exception as e:
            print(f"Ошибка при обновлении UI удаления: {e}")

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

            # Сбрасываем все чекбоксы
            for checkbox in self.pair_widgets.values():
                if checkbox:
                    checkbox.setChecked(False)

            self.update_deletion_ui()
            self.log_text.append("✅ Все отметки удаления очищены")

    # =============================================================================
    # МЕТОДЫ ДЛЯ ВКЛАДКИ СКАНИРОВАНИЯ
    # =============================================================================

    def select_folder(self):
        """Выбирает папку для сканирования"""
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
            self.selected_folder = folder
            self.selected_folder_label.setText(f"Выбрана: {os.path.basename(folder)}")
            self.log_text.append(f"📁 Выбрана папка: {folder}")

    def start_optimized_scan(self):
        """Запускает оптимизированное сканирование папки"""
        if not self.selected_folder:
            self.show_warning("Сначала выберите папку для сканирования!")
            return

        # Получаем и проверяем порог схожести
        try:
            threshold_text = self.similarity_threshold_input.text()
            threshold = float(threshold_text) if threshold_text else Config.SIMILARITY_THRESHOLD
            if not (0.1 <= threshold <= 1.0):
                raise ValueError("Порог должен быть между 0.1 и 1.0")
        except ValueError as e:
            self.show_warning(f"Некорректный порог схожести: {e}")
            return

        # Блокируем UI на время сканирования
        self.set_scan_ui_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Очищаем предыдущие кнопки групп
        self.clear_pair_buttons()

        self.log_text.clear()
        self.log_text.append("🚀 ЗАПУСК ОПТИМИЗИРОВАННОГО СКАНИРОВАНИЯ")
        self.log_text.append(f"📁 Папка: {self.selected_folder}")
        self.log_text.append(f"🎯 Порог схожести: {threshold:.0%}")
        self.log_text.append("─" * 50)

        # Запускаем сканирование в отдельном потоке
        self.optimized_scan_thread = OptimizedScanThread(
            self.comparator,
            self.selected_folder,
            threshold
        )
        self.optimized_scan_thread.progress_signal.connect(self.update_optimized_progress)
        self.optimized_scan_thread.result_signal.connect(self.optimized_scan_finished)
        self.optimized_scan_thread.finished_signal.connect(self.scan_thread_finished)
        self.optimized_scan_thread.start()

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

        self.log_text.append(f"📊 Найдено пар похожих видео: {len(results)}")
        self.status_label.setText(f"Найдено {len(results)} пар похожих видео")

        # Сохраняем все пары для последующего использования
        self.current_pairs = results

        # Показываем СВОДКУ пар в логе (не все детали)
        high_similarity = sum(1 for _, _, sim, _ in results if sim > 0.8)
        medium_similarity = sum(1 for _, _, sim, _ in results if 0.6 <= sim <= 0.8)
        low_similarity = sum(1 for _, _, sim, _ in results if sim < 0.6)

        self.log_text.append(f"🎯 Высокая схожесть (>80%): {high_similarity} пар")
        self.log_text.append(f"📗 Средняя схожесть (60-80%): {medium_similarity} пар")
        self.log_text.append(f"📉 Низкая схожесть (<60%): {low_similarity} пар")

        # Создаем кнопки для сравнения КАЖДОЙ пары
        self.create_pair_buttons(results)

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
            self.pair_widgets[video_path] = checkbox

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
        """Отмечает/снимает отметку файла для удаления БЕЗ немедленного обновления UI"""
        try:
            if marked:
                self.marked_for_deletion.add(file_path)
            else:
                self.marked_for_deletion.discard(file_path)

            # ОТЛАДКА: логируем изменение
            print(f"DEBUG: toggle_mark_deletion - файлов отмечено: {len(self.marked_for_deletion)}")

            # Обновляем UI с небольшой задержкой чтобы избежать накопления вызовов
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(10, self.update_deletion_ui)

        except Exception as e:
            print(f"Ошибка в toggle_mark_deletion: {e}")

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
        """Обрабатывает удаление файла из диалога сравнения"""
        # Удаляем файл из отмеченных, если он там есть
        self.marked_for_deletion.discard(video_path)

        # Удаляем пары, содержащие удаленный файл
        self.current_pairs = [pair for pair in self.current_pairs
                              if video_path not in (pair[0], pair[1])]

        # Обновляем UI
        self.update_deletion_ui()
        self.create_pair_buttons(self.current_pairs)
        self.log_text.append(f"🗑️ Файл удален из диалога: {os.path.basename(video_path)}")

    def open_comparison_dialog(self, video_paths):
        """Открывает side-by-side сравнение для выбранной пары"""
        if len(video_paths) < 2:
            self.show_warning("Для сравнения нужно как минимум 2 видеофайла!")
            return

        try:
            from src.gui.comparison_dialog import ComparisonDialog
            dialog = ComparisonDialog(video_paths, self)
            # Подключаем сигнал удаления файла
            dialog.file_deleted.connect(self.on_video_deleted)
            dialog.exec()
        except Exception as e:
            print(f"Ошибка при открытии ComparisonDialog: {e}")
            # Fallback на простой диалог
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
            for checkbox in self.pair_widgets.values():
                if checkbox:
                    try:
                        checkbox.toggled.disconnect()
                    except:
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
        """Выбирает видеофайл для сравнения"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Выберите видео файл #{video_num}",
            "",
            f"Video Files ({' '.join(['*' + fmt for fmt in Config.SUPPORTED_FORMATS])})"  # Используем конфиг
        )
        if file_path:
            if video_num == 1:
                self.video1_path = file_path
                self.video1_label.setText(f"Выбрано: {os.path.basename(file_path)}")
            else:
                self.video2_path = file_path
                self.video2_label.setText(f"Выбрано: {os.path.basename(file_path)}")

    def compare_selected_videos(self):
        """Сравнивает два выбранных видеофайла"""
        if not self.video1_path or not self.video2_path:
            self.show_warning("Выберите оба видеофайла для сравнения!")
            return

        self.compare_results.clear()
        self.compare_results.append("🔄 Начинаем сравнение...")

        # Запускаем сравнение в отдельном потоке
        self.compare_thread = CompareThread(self.comparator, self.video1_path, self.video2_path)
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


# =============================================================================
# ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ
# =============================================================================

def main():
    """Основная функция запуска приложения"""
    # Создаем приложение
    app = QApplication(sys.argv)
    app.setApplicationName("VideoDuplicate Cleaner")
    app.setApplicationVersion("1.0")

    # Создаем и показываем главное окно
    window = MainWindow()
    window.show()

    # Запускаем цикл событий
    sys.exit(app.exec())


if __name__ == "__main__":
    main()