OdeD -- GroundLM 2026 Shared Task 2 (LitTraceQA)
Final test output for the REQUIRED track: evaluator task `littraceqa-test`.

littraceqa-test_OdeD.jsonl
  71 predictions, one per query_id in the released input-only test split.
  This is the exact run whose official evaluator output is reported in the
  system paper (Table 3, final row):

    paper_precision_macro      0.985915
    paper_recall_macro         0.968310
    paper_f1_macro             0.970423
    evidence_precision_macro   0.733568
    evidence_recall_macro      0.753521
    evidence_f1_macro          0.731858
    multiple_choice_accuracy   0.980000
    freeform_exact_match       null
    table_row_f1_macro         0.499206
    table_cell_accuracy_macro  0.297619
    table_cell_accuracy_micro  0.356322

    overall = (paper_f1 + evidence_f1 + (mc + row_f1 + cell_acc)/3)/3 = 0.7649

We did not submit to the optional `littraceqa-test-extra` diagnostic track, so
this archive contains one file.
