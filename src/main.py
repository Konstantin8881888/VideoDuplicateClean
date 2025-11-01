import sys
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QFileDialog, QTextEdit, QProgressBar, QTabWidget, QHBoxLayout,
    QLineEdit, QMessageBox, QScrollArea  # Добавляем QScrollArea
)
from PyQt6.QtCore import QThread, pyqtSignal, QUrl
from src.config import Config

# Импорты наших модулей
from src.core.file_scanner import FileScanner
from src.core.frame_extractor import FrameExtractor
from src.core.optimized_comparator import OptimizedVideoComparator


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
        self.setGeometry(100, 100, 900, 700)

        # Инициализация компонентов
        self.scanner = FileScanner()
        self.frame_extractor = FrameExtractor()
        self.comparator = OptimizedVideoComparator()  # Используем оптимизированную версию

        # Переменные состояния
        self.selected_folder = ""
        self.video1_path = ""
        self.video2_path = ""
        self.current_pairs = []
        self.optimized_scan_thread = None
        self.compare_thread = None
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
        """Создает вкладку для сканирования папки с прокруткой"""
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

        # Поле для логов и результатов
        self.log_text = QTextEdit()
        self.log_text.setPlaceholderText(
            "Здесь будут отображаться процесс сканирования и результаты...\n\n"
            "Оптимизированный алгоритм:\n"
            "• Сначала ищет точные дубликаты по хэшам\n"
            "• Фильтрует по метаданным (размер, длительность)\n"
            "• Только затем делает глубокий анализ кадров"
        )
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)  # Ограничиваем высоту лога
        layout.addWidget(self.log_text)

        # Заголовок для списка пар
        pairs_label = QLabel("🎯 Найденные пары для сравнения:")
        pairs_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(pairs_label)

        # ПРОКРУЧИВАЕМАЯ ОБЛАСТЬ ДЛЯ КНОПОК ПАР
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(300)  # Минимальная высота
        scroll_area.setMaximumHeight(600)  # Максимальная высота

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
        """Создает кнопки для сравнения КАЖДОЙ пары отдельно в прокручиваемой области"""
        # Очищаем предыдущие кнопки
        self.clear_pair_buttons()

        for i, (video1, video2, similarity, details) in enumerate(pairs, 1):
            file1 = os.path.basename(video1)
            file2 = os.path.basename(video2)
            size1 = os.path.getsize(video1) / (1024 * 1024)
            size2 = os.path.getsize(video2) / (1024 * 1024)

            # Создаем информативную кнопку
            pair_btn = QPushButton(
                f"🔍 Пара {i}: {similarity:.1%} схожести\n"
                f"📹 {file1} ({size1:.1f}MB)\n"
                f"📹 {file2} ({size2:.1f}MB)"
            )
            pair_btn.clicked.connect(lambda checked, v1=video1, v2=video2: self.open_comparison_dialog([v1, v2]))
            pair_btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 8px;
                    margin: 2px;
                    background-color: #f0f0f0;
                    border: 1px solid #ccc;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
            """)
            self.pairs_layout.addWidget(pair_btn)

        # Добавляем растягивающийся элемент в конец
        self.pairs_layout.addStretch()

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

    def open_comparison_dialog(self, video_paths):
        """Открывает side-by-side сравнение для выбранной пары"""
        if len(video_paths) < 2:
            self.show_warning("Для сравнения нужно как минимум 2 видеофайла!")
            return

        try:
            # Пробуем открыть полноценный side-by-side диалог
            from src.gui.comparison_dialog import ComparisonDialog
            dialog = ComparisonDialog(video_paths, self)
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
                # Минимальный fallback
                self.show_pair_info(video_paths)

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
        """Очищает кнопки пар"""
        if hasattr(self, 'pairs_layout') and self.pairs_layout:
            # Удаляем все виджеты из layout
            for i in reversed(range(self.pairs_layout.count())):
                item = self.pairs_layout.itemAt(i)
                if item and item.widget():
                    item.widget().setParent(None)
                    item.widget().deleteLater()

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
        """Обрабатывает закрытие приложения"""
        # Останавливаем потоки если они работают
        if self.optimized_scan_thread and self.optimized_scan_thread.isRunning():
            self.optimized_scan_thread.terminate()
            self.optimized_scan_thread.wait()

        if self.compare_thread and self.compare_thread.isRunning():
            self.compare_thread.terminate()
            self.compare_thread.wait()

        event.accept()


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