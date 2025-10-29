import sys
import os
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel,
    QFileDialog, QTextEdit, QProgressBar, QTabWidget, QHBoxLayout,
    QLineEdit, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QUrl

# Импорты наших модулей
from core.file_scanner import FileScanner
from core.frame_extractor import FrameExtractor
from core.optimized_comparator import OptimizedVideoComparator


# =============================================================================
# КЛАССЫ ДЛЯ МНОГОПОТОЧНОСТИ
# =============================================================================

class OptimizedScanThread(QThread):
    """Поток для оптимизированного сканирования папки"""

    # Сигналы для обновления UI из потока
    progress_signal = pyqtSignal(int, str)  # прогресс (проценты, сообщение)
    result_signal = pyqtSignal(list)  # финальные результаты
    finished_signal = pyqtSignal()  # завершение работы

    def __init__(self, comparator, folder_path, similarity_threshold=0.7):
        super().__init__()
        self.comparator = comparator
        self.folder_path = folder_path
        self.similarity_threshold = similarity_threshold
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
        self.current_groups = []
        self.optimized_scan_thread = None
        self.compare_thread = None

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
        """Создает вкладку для сканирования папки"""
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
        self.similarity_threshold_input = QLineEdit("0.7")
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
        layout.addWidget(self.log_text)

        # Кнопки для групп (будем создавать динамически)
        self.groups_layout = QVBoxLayout()
        layout.addLayout(self.groups_layout)

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
            threshold = float(self.similarity_threshold_input.text())
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
        self.clear_group_buttons()

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
        """Обрабатывает результаты оптимизированного сканирования"""
        self.log_text.append("\n" + "═" * 50)
        self.log_text.append("✅ СКАНИРОВАНИЕ ЗАВЕРШЕНО!")

        if not results:
            self.log_text.append("❌ Похожих видеофайлов не найдено")
            self.status_label.setText("Похожие видео не найдены")
            return

        # Группируем результаты для удобного отображения
        groups = self._group_similar_videos(results)

        self.log_text.append(f"📊 Найдено групп похожих видео: {len(groups)}")
        self.log_text.append(f"📈 Всего пар: {len(results)}")
        self.status_label.setText(f"Найдено {len(groups)} групп похожих видео")

        # Сохраняем группы для последующего использования
        self.current_groups = groups

        # Показываем группы с вычислением средней схожести
        for i, group in enumerate(groups, 1):
            # Вычисляем среднюю схожесть для группы
            total_similarity = 0
            for video_path, similarity in group:
                total_similarity += similarity
            avg_similarity = total_similarity / len(group) if group else 0

            self.log_text.append(f"\n🎬 ГРУППА {i} ({len(group)} видео, средняя схожесть: {avg_similarity:.1%}):")

            for video_path, similarity in group:
                file_size = os.path.getsize(video_path) / (1024 * 1024)  # в MB
                self.log_text.append(
                    f"   📹 {os.path.basename(video_path)} ({file_size:.1f} MB, схожесть: {similarity:.1%})")

        # Создаем кнопки для сравнения групп с указанием средней схожести
        self.create_group_buttons(groups)

    def create_group_buttons(self, groups):
        """Создает кнопки для сравнения групп с указанием процента схожести"""
        for i, group in enumerate(groups, 1):
            # Вычисляем среднюю схожесть для группы
            total_similarity = 0
            for video_path, similarity in group:
                total_similarity += similarity
            avg_similarity = total_similarity / len(group) if group else 0

            compare_btn = QPushButton(f"🔍 Сравнить группу {i} (схожесть: {avg_similarity:.1%})")
            compare_btn.clicked.connect(lambda checked, idx=i - 1: self.open_group_comparison(idx))
            self.groups_layout.addWidget(compare_btn)

    def clear_group_buttons(self):
        """Очищает кнопки групп"""
        # Удаляем все кнопки из layout
        for i in reversed(range(self.groups_layout.count())):
            widget = self.groups_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

    def open_group_comparison(self, group_index):
        """Открывает сравнение для выбранной группы"""
        if 0 <= group_index < len(self.current_groups):
            group = self.current_groups[group_index]
            video_paths = [video_path for video_path, similarity in group]

            if len(video_paths) >= 2:
                self.open_comparison_dialog(video_paths)
            else:
                self.show_warning("В группе должно быть как минимум 2 видео для сравнения")
        else:
            self.show_warning("Группа не найдена")

    def open_comparison_dialog(self, video_paths):
        """Открывает диалог для side-by-side сравнения видео"""
        if len(video_paths) < 2:
            self.show_warning("Для сравнения нужно как минимум 2 видеофайла!")
            return

        try:
            # Пробуем импортировать и открыть диалог сравнения
            from src.gui.comparison_dialog import ComparisonDialog
            dialog = ComparisonDialog(video_paths, self)
            dialog.exec()
        except ImportError as e:
            print(f"Ошибка импорта: {e}")
            self.show_simple_comparison(video_paths)
        except Exception as e:
            print(f"Ошибка при открытии диалога: {e}")
            self.show_simple_comparison(video_paths)

    def show_simple_comparison(self, video_paths):
        """Показывает упрощенное сравнение если основной диалог не работает"""
        info = "Side-by-Side сравнение\n\n"
        info += "Сравниваемые файлы:\n"
        for i, path in enumerate(video_paths[:2]):  # Берем только первые 2
            if os.path.exists(path):
                size = os.path.getsize(path) / (1024 * 1024)
                info += f"\n{i + 1}. {os.path.basename(path)}\n"
                info += f"   Размер: {size:.2f} MB\n"
                info += f"   Путь: {path}\n"
            else:
                info += f"\n{i + 1}. ФАЙЛ НЕ НАЙДЕН: {path}\n"

        self.log_text.append(f"\n🔍 СРАВНЕНИЕ ГРУППЫ:\n{info}")

    def scan_thread_finished(self):
        """Вызывается когда поток сканирования завершил работу"""
        self.set_scan_ui_enabled(True)
        self.progress_bar.setVisible(False)

    def _group_similar_videos(self, results: list) -> list:
        """Группирует похожие видео в логические группы"""
        groups = []
        used_videos = set()

        for video1, video2, similarity, _ in results:
            # Если оба видео уже в группах, пропускаем
            if video1 in used_videos and video2 in used_videos:
                continue

            # Ищем существующую группу для одного из видео
            found_group = None
            for group in groups:
                group_videos = [v[0] for v in group]
                if video1 in group_videos or video2 in group_videos:
                    found_group = group
                    break

            # Если группы нет, создаем новую
            if found_group is None:
                found_group = []
                groups.append(found_group)

            # Добавляем видео в группу если их там еще нет
            if video1 not in used_videos:
                found_group.append((video1, similarity))
                used_videos.add(video1)

            if video2 not in used_videos:
                found_group.append((video2, similarity))
                used_videos.add(video2)

        return groups

    # =============================================================================
    # МЕТОДЫ ДЛЯ ВКЛАДКИ СРАВНЕНИЯ
    # =============================================================================

    def select_video_for_comparison(self, video_num: int):
        """Выбирает видеофайл для сравнения"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Выберите видео файл #{video_num}",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv)"
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