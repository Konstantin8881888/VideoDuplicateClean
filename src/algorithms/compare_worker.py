import argparse
import json
import os
import sys
import traceback

def safe_add_project_root_to_syspath():
    # __file__ == .../repo/src/algorithms/compare_worker.py
    script_dir = os.path.dirname(os.path.abspath(__file__))              # .../repo/src/algorithms
    # project_root = go up three levels -> .../repo
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # additionally set cwd to project_root (helps относительным импортам и путям)
    try:
        os.chdir(project_root)
    except Exception:
        pass
    return project_root

def main():
    parser = argparse.ArgumentParser(description="Compare two videos using a chosen algorithm and output JSON result")
    parser.add_argument("--alg", required=True, help="Algorithm name (simple, phash, cnn_faiss)")
    parser.add_argument("--v1", required=True, help="Path to first video")
    parser.add_argument("--v2", required=True, help="Path to second video")
    parser.add_argument("--max-frames", type=int, default=10, help="Max frames for comparison")
    parser.add_argument("--phash-frames", type=int, default=None)
    parser.add_argument("--phash-ham", type=int, default=None)
    args = parser.parse_args()

    project_root = safe_add_project_root_to_syspath()

    try:
        # импортируем фабрику алгоритмов (после добавления project_root в sys.path)
        from src.algorithms import create_algorithm
    except Exception as e:
        tb = traceback.format_exc()
        out = {'similarity': 0.0, 'error': f'create_algorithm_import_error: {e}', 'traceback': tb, 'frame_comparisons': []}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(0)

    alg = create_algorithm(args.alg)

    # если phash, применим дополнительные параметры
    try:
        if args.alg.lower() == 'phash' and alg is not None:
            if args.phash_frames is not None and hasattr(alg, 'frames_to_sample'):
                alg.frames_to_sample = int(args.phash_frames)
            if args.phash_ham is not None and hasattr(alg, 'ham_thresh'):
                alg.ham_thresh = int(args.phash_ham)
    except Exception:
        # не фатально — продолжим
        pass

    try:
        res = alg.compare_videos(args.v1, args.v2, max_frames=args.max_frames)
        # Убедимся, что вывод сериализуем (заменим не-сериализуемые вещи)
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        tb = traceback.format_exc()
        out = {'similarity': 0.0, 'error': f'worker_exception: {e}', 'traceback': tb, 'frame_comparisons': []}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(0)

if __name__ == "__main__":
    main()