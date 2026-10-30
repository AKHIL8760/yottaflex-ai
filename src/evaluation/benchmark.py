"""
Ground-truth benchmarking and evaluation suite for payment reconciliation.
Calculates Precision, Recall, F1 score, break detection accuracy, and financial variance metrics.
"""
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict
from src.models.entities import GroundTruthAnomaly, ExceptionRecord, ReconciliationMatch


class GroundTruthBenchmark:
    """
    Evaluates reconciliation engine performance against the segregated ground truth dataset.
    Never exposes ground truth labels to the matching or decision logic.
    """

    def __init__(
        self,
        ground_truth: List[GroundTruthAnomaly],
        exceptions: List[ExceptionRecord],
        matches: List[ReconciliationMatch],
    ):
        self.ground_truth = ground_truth
        self.exceptions = exceptions
        self.matches = matches

    def evaluate(self) -> Dict[str, Any]:
        """
        Computes precision, recall, F1-score, and per-anomaly-type breakdown.
        """
        # Ground truth lookup: (issue_type, entity_id)
        gt_pairs: Set[Tuple[str, str]] = {(gt.issue_type, gt.entity_id) for gt in self.ground_truth}
        gt_by_type: Dict[str, int] = defaultdict(int)
        for gt in self.ground_truth:
            gt_by_type[gt.issue_type] += 1

        # Detected exceptions lookup
        detected_pairs: Set[Tuple[str, str]] = set()
        detected_by_type: Dict[str, int] = defaultdict(int)

        for exc in self.exceptions:
            detected_pairs.add((exc.issue_type, exc.entity_id))
            detected_by_type[exc.issue_type] += 1

        # Count True Positives, False Positives, False Negatives
        tp_by_type: Dict[str, int] = defaultdict(int)
        for issue_type, entity_id in gt_pairs:
            # Check direct match or entity match
            matched = False
            for exc in self.exceptions:
                if exc.issue_type == issue_type and (
                    exc.entity_id == entity_id
                    or exc.related_entity_id == entity_id
                    or (issue_type == "DUPLICATE_SETTLEMENT_LINE" and entity_id.startswith(exc.entity_id.split("-DUP")[0]))
                    or (issue_type == "DUPLICATE_WEBHOOK_INGESTED" and exc.entity_id == entity_id)
                ):
                    matched = True
                    break

            if matched:
                tp_by_type[issue_type] += 1

        total_tp = sum(tp_by_type.values())
        total_gt = len(self.ground_truth)
        total_detected = len(self.exceptions)

        total_fn = max(0, total_gt - total_tp)
        total_fp = max(0, total_detected - total_tp)

        precision = round(total_tp / total_detected, 4) if total_detected > 0 else 0.0
        recall = round(total_tp / total_gt, 4) if total_gt > 0 else 0.0
        f1_score = (
            round(2 * (precision * recall) / (precision + recall), 4)
            if (precision + recall) > 0
            else 0.0
        )

        # Per category metrics
        category_breakdown = {}
        all_issue_types = sorted(list(set(list(gt_by_type.keys()) + list(detected_by_type.keys()))))

        for itype in all_issue_types:
            c_gt = gt_by_type.get(itype, 0)
            c_det = detected_by_type.get(itype, 0)
            c_tp = tp_by_type.get(itype, 0)
            c_fn = max(0, c_gt - c_tp)
            c_fp = max(0, c_det - c_tp)

            c_prec = round(c_tp / c_det, 4) if c_det > 0 else 0.0
            c_rec = round(c_tp / c_gt, 4) if c_gt > 0 else 0.0
            c_f1 = (
                round(2 * (c_prec * c_rec) / (c_prec + c_rec), 4)
                if (c_prec + c_rec) > 0
                else 0.0
            )

            category_breakdown[itype] = {
                "ground_truth_count": c_gt,
                "detected_count": c_det,
                "true_positives": c_tp,
                "false_positives": c_fp,
                "false_negatives": c_fn,
                "precision": c_prec,
                "recall": c_rec,
                "f1_score": c_f1,
            }

        # Financial Discrepancy Statistics
        total_matched_volume = sum(m.left_amount for m in self.matches)
        total_discrepancy = sum(exc.discrepancy_amount for exc in self.exceptions)

        return {
            "overall_metrics": {
                "total_ground_truth_anomalies": total_gt,
                "total_exceptions_detected": total_detected,
                "true_positives": total_tp,
                "false_positives": total_fp,
                "false_negatives": total_fn,
                "precision": precision,
                "recall": recall,
                "f1_score": f1_score,
                "detection_accuracy_percentage": round(recall * 100, 2),
            },
            "financial_metrics": {
                "total_matched_financial_volume": round(total_matched_volume, 2),
                "total_discrepancy_identified": round(total_discrepancy, 2),
                "match_rate_percentage": round(
                    (len(self.matches) / (len(self.matches) + total_detected)) * 100, 2
                )
                if (len(self.matches) + total_detected) > 0
                else 0.0,
            },
            "category_breakdown": category_breakdown,
        }
