# debug_phash_run.py
import sys
from src.algorithms.phash import PHashAlgorithm

if __name__ == "__main__":
    # поменяйте пути на 2-4 файла из вашей тестовой папки
    files = [
        r"D:\Margo\video574.mp4",
        r"D:\Margo\video.mp4",
        r"D:\Margo\video5.mp4",
    ]
    alg = PHashAlgorithm(frames_to_sample=10)
    print("Starting phash run")
    res = alg.find_similar_videos_optimized(files, similarity_threshold=0.2)
    print("Result:", res)
    print("Done")
