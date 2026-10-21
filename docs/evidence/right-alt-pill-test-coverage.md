# S6 replacement coverage before retiring legacy tests

All replacement tests below passed before removal.

| Legacy behavior | Replacement evidence |
|---|---|
| DPI on a new display / fixed anchor after Copy | test_each_new_pill_samples_display_dpi_and_keeps_frozen_bounds_during_copy; test_pill_and_future_panel_fit_work_area_with_scaled_margin (9 parameter cases) |
| Expanded window remains inside work area; bottom-center ignores pointer | test_pill_and_future_panel_fit_work_area_with_scaled_margin; test_bottom_center_placement_does_not_follow_pointer |
| Complete recognized text, recovery, Copy pending/success/failure | test_panel_keeps_full_text_and_copy_updates_reuse_widgets_without_moving_pill; test_copy_label_golden; test_failed_refinement_preserves_raw_copy_and_disables_refinement |
| Window lease/interaction matching, late result/close, frozen callbacks, injected native port | test_owner_ignores_late_result_and_close_for_replaced_interaction; test_callbacks_keep_original_interaction_and_native_port_when_replaced |
| Terminal dwell and delayed failure close | test_terminal_dwell_schedules_one_identity_scoped_dismiss (600/1200); test_closed_message_flashes_for_three_seconds_without_closing_replacement |
| Esc cancels only matching operation | test_callbacks_keep_original_interaction_and_native_port_when_replaced; test_stale_view_commands_cannot_confirm_or_cancel_the_new_interaction; existing refinement/paste cancellation journeys |
| Nonactivating show / preserved foreground and input focus | test_show_captures_once_before_native_nonactivating_show_and_lock; test_pill_show_preserves_controlled_native_foreground_and_focused_entry |
| Legacy activation/Enter/Ctrl+P behavior intentionally superseded by X3 | test_show_captures_once_before_native_nonactivating_show_and_lock verifies bindings absent; native foreground test verifies no activation |
| Pending vs admitted refinement, cancellation, readable failure | test_refinement_admission_is_reported_back_to_the_view_owner; phase/status/spinner golden tables; closed message golden; cancel timeout controller test |
| Popup measured word/countdown, animation lifecycle | test_popup_raster_leaves_room_for_measured_word_and_formats_countdown; test_popup_voice_indicator_renders_raster_shapes_and_animates_only_active_work |

Evidence: mu-s6-native-focus: 7 integration passed; mu-s6-one-root: 6 integration passed; latest owner/visual run: 50 passed. No screen pixels or user text saved.

S8 final: native wrapper style after mapping and root raster resource lifetime now have additional integration coverage in tests/ui/test_inline_pill.py (9 passed). External click evidence: artifacts/mu-s8-focus-mapped.jsonl (6/6). Final acceptance: artifacts/mu-s8-release.jsonl.
