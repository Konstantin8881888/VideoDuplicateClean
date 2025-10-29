import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt


class SimpleComparisonDialog(QDialog):
    """Упрощенный диалог для тестирования интеграции"""

    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths

        self.setWindowTitle("Side-by-Side Сравнение (Тест)")
        self.setGeometry(100, 100, 800, 600)
        self.setup_ui()

    def setup_ui(self):
        """Создает упрощенный интерфейс"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Заголовок
        title = QLabel("🎬 Side-by-Side Сравнение Видео")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Информация о файлах
        info_text = QTextEdit()
        info_text.setPlainText(
            f"Сравниваем файлы:\n"
            f"1. {os.path.basename(self.video_paths[0])}\n"
            f"2. {os.path.basename(self.video_paths[1])}\n\n"
            f"Полная версия сравнения будет реализована позже."
        )
        info_text.setReadOnly(True)
        layout.addWidget(info_text)

        # Кнопки
        button_layout = QHBoxLayout()

        test_btn = QPushButton("Тест: Показать информацию")
        test_btn.clicked.connect(self.show_info)
        button_layout.addWidget(test_btn)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def show_info(self):
        """Показывает информацию о файлах"""
        info = "Информация о файлах:\n\n"
        for i, path in enumerate(self.video_paths):
            if os.path.exists(path):
                size = os.path.getsize(path) / (1024 * 1024)  # MB
                info += f"Файл {i + 1}: {os.path.basename(path)}\n"
                info += f"Размер: {size:.2f} MB\n"
                info += f"Путь: {path}\n\n"
            else:
                info += f"Файл {i + 1}: НЕ НАЙДЕН - {path}\n\n"

        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Информация о файлах", info)