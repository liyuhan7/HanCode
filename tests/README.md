# 测试

根据 TDD（测试驱动开发）原则，实现任务必须先写失败测试，再写最小实现。

最终测试套件必须证明 Harness 控制流有效，而不是证明模型能力。核心路径应使用
MockLLM 或 stub，无网络、无真实 LLM。

课程项目场景至少覆盖：

- `test_spec_phase_rejects_edit_file`
- `test_plan_required_before_code_phase`
- `test_code_phase_allows_edit_file`
- `test_edit_file_requires_reason`
- `test_edit_file_creates_checkpoint`
- `test_rollback_last_checkpoint_restores_file`
- `test_workspace_has_separate_history`
- `test_tool_not_allowed_in_workspace_is_denied`
- `test_code_change_requires_test_or_risk_note`
- `test_max_steps_prevents_infinite_loop`
- `test_deliver_requires_knowledge_file`
- `test_deliver_requires_deliverables_file`
- `test_context_builder_includes_course_context`
- `test_policy_protects_assignment_files`
- `test_policy_protects_teacher_tests_or_grading_scripts`
