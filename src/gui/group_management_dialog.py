import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTabWidget, QWidget, QTextEdit,
    QMessageBox, QProgressBar, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


class GroupAnalysisThread(QThread):
    """Поток для анализа группы видео"""

    progress_signal = pyqtSignal(int, str)
    analysis_complete = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, comparator, video_paths):
        super().__init__()
        self.comparator = comparator
        self.video_paths = video_paths

    def run(self):
        try:
            results = {}
            total = len(self.video_paths)

            # Анализируем все попарные комбинации в группе
            for i, video1 in enumerate(self.video_paths):
                self.progress_signal.emit(int((i / total) * 100), f"Анализируем {os.path.basename(video1)}...")

                for j, video2 in enumerate(self.video_paths[i + 1:], i + 1):
                    if video1 != video2:
                        result = self.comparator.compare_videos(video1, video2)
                        key = tuple(sorted([video1, video2]))
                        results[key] = result

            self.analysis_complete.emit(results)

        except Exception as e:
            self.error_signal.emit(f"Ошибка анализа группы: {e}")


class GroupManagementDialog(QDialog):
    """Диалог для управления и сравнения видео в группе"""

    def __init__(self, group_videos, comparator, parent=None):
        super().__init__(parent)
        self.group_videos = group_videos
        self.comparator = comparator
        self.pairwise_results = {}

        self.setWindowTitle(f"Управление группой ({len(group_videos)} видео)")
        self.setGeometry(100, 50, 1200, 800)
        self.setup_ui()

        # Запускаем анализ группы
        self.analyze_group()

    def setup_ui(self):
        """Создает интерфейс управления группой"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Заголовок
        title_label = QLabel(f"🎬 Управление группой из {len(self.group_videos)} видео")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Сплиттер для разделения экрана
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Левая панель - список видео
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)

        left_layout.addWidget(QLabel("📁 Видео в группе:"))
        self.video_list = QListWidget()
        for video_path in self.group_videos:
            item = QListWidgetItem(f"{os.path.basename(video_path)}")
            item.setData(Qt.ItemDataRole.UserRole, video_path)
            self.video_list.addItem(item)
        left_layout.addWidget(self.video_list)

        # Кнопки выбора
        select_buttons_layout = QHBoxLayout()
        self.select_pair_btn = QPushButton("Выбрать пару для сравнения")
        self.select_pair_btn.clicked.connect(self.select_pair_for_comparison)
        self.select_pair_btn.setEnabled(False)
        select_buttons_layout.addWidget(self.select_pair_btn)

        self.select_all_btn = QPushButton("Сравнить все попарно")
        self.select_all_btn.clicked.connect(self.compare_all_pairs)
        self.select_all_btn.setEnabled(False)
        select_buttons_layout.addWidget(self.select_all_btn)

        left_layout.addLayout(select_buttons_layout)

        # Правая панель - результаты
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)

        right_layout.addWidget(QLabel("📊 Результаты анализа:"))

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        right_layout.addWidget(self.progress_bar)

        # Статус
        self.status_label = QLabel("Анализируем группу...")
        right_layout.addWidget(self.status_label)

        # Результаты попарного сравнения
        self.results_text = QTextEdit()
        self.results_text.setPlaceholderText("Результаты попарного сравнения появятся здесь...")
        right_layout.addWidget(self.results_text)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 800])

        # Кнопки управления
        button_layout = QHBoxLayout()

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def analyze_group(self):
        """Запускает анализ всех попарных комбинаций в группе"""
        self.analysis_thread = GroupAnalysisThread(self.comparator, self.group_videos)
        self.analysis_thread.progress_signal.connect(self.update_progress)
        self.analysis_thread.analysis_complete.connect(self.on_analysis_complete)
        self.analysis_thread.error_signal.connect(self.on_analysis_error)
        self.analysis_thread.start()

    def update_progress(self, value: int, message: str):
        """Обновляет прогресс анализа"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def on_analysis_complete(self, results):
        """Обрабатывает завершение анализа"""
        self.pairwise_results = results
        self.progress_bar.setVisible(False)
        self.status_label.setText("Анализ завершен!")
        self.select_pair_btn.setEnabled(True)
        self.select_all_btn.setEnabled(True)

        # Показываем сводку результатов
        self.show_results_summary()

    def on_analysis_error(self, error_message):
        """Обрабатывает ошибки анализа"""
        self.status_label.setText(f"Ошибка: {error_message}")
        QMessageBox.critical(self, "Ошибка анализа", error_message)

    def show_results_summary(self):
        """Показывает сводку результатов попарного сравнения"""
        if not self.pairwise_results:
            self.results_text.setText("Нет результатов для отображения")
            return

        summary = "📊 СВОДКА ПОПАРНОГО СРАВНЕНИЯ:\n\n"

        # Группируем по уровням схожести
        high_similarity = []  # > 0.8
        medium_similarity = []  # 0.6 - 0.8
        low_similarity = []  # < 0.6

        for (video1, video2), result in self.pairwise_results.items():
            similarity = result.get('similarity', 0)
            pair_info = f"{os.path.basename(video1)} ↔ {os.path.basename(video2)}: {similarity:.1%}"

            if similarity > 0.8:
                high_similarity.append(pair_info)
            elif similarity > 0.6:
                medium_similarity.append(pair_info)
            else:
                low_similarity.append(pair_info)

        summary += f"🎯 ВЫСОКАЯ СХОЖЕСТЬ (>80%): {len(high_similarity)} пар\n"
        for pair in high_similarity:
            summary += f"   ✅ {pair}\n"

        summary += f"\n📗 СРЕДНЯЯ СХОЖЕСТЬ (60-80%): {len(medium_similarity)} пар\n"
        for pair in medium_similarity:
            summary += f"   🔸 {pair}\n"

        summary += f"\n📉 НИЗКАЯ СХОЖЕСТЬ (<60%): {len(low_similarity)} пар\n"
        for pair in low_similarity:
            summary += f"   🔻 {pair}\n"

        self.results_text.setText(summary)

    def select_pair_for_comparison(self):
        """Позволяет выбрать пару для детального сравнения"""
        selected_items = self.video_list.selectedItems()
        if len(selected_items) != 2:
            QMessageBox.warning(self, "Выбор пары", "Пожалуйста, выберите ровно два видео для сравнения")
            return

        video1 = selected_items[0].data(Qt.ItemDataRole.UserRole)
        video2 = selected_items[1].data(Qt.ItemDataRole.UserRole)

        self.open_comparison_dialog([video1, video2])

    def compare_all_pairs(self):
        """Сравнивает все пары и показывает детальные результаты"""
        detailed_results = "🔍 ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ ВСЕХ ПАР:\n\n"

        for (video1, video2), result in self.pairwise_results.items():
            similarity = result.get('similarity', 0)
            detailed_results += f"🎬 {os.path.basename(video1)} ↔ {os.path.basename(video2)}\n"
            detailed_results += f"   Схожесть: {similarity:.2%}\n"

            if 'frame_comparisons' in result:
                detailed_results += f"   Сравнений кадров: {len(result['frame_comparisons'])}\n"

                # Показываем топ-3 самых похожих кадров
                top_frames = sorted(result['frame_comparisons'],
                                    key=lambda x: x.get('similarity', 0), reverse=True)[:3]
                for i, frame_comp in enumerate(top_frames, 1):
                    detailed_results += f"     Кадр {i}: {frame_comp.get('similarity', 0):.2%}\n"

            detailed_results += "\n"

        self.results_text.setText(detailed_results)

    def open_comparison_dialog(self, video_paths):
        """Открывает диалог сравнения для выбранной пары"""
        try:
            from src.gui.comparison_dialog import ComparisonDialog
            dialog = ComparisonDialog(video_paths, self)
            dialog.exec()
        except Exception as e:
            print(f"Ошибка при открытии ComparisonDialog: {e}")
            # Резервный вариант - используем SimpleComparisonDialog
            try:
                from src.gui.simple_comparison_dialog import SimpleComparisonDialog
                QMessageBox.information(self, "Информация", "Используется упрощенный режим сравнения")
                dialog = SimpleComparisonDialog(video_paths, self)
                dialog.exec()
            except Exception as e2:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть сравнение: {e2}")