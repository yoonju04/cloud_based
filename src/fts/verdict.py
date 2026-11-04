"""Pre-declared verdict policy.

The policy runs before anyone looks at a particular outcome and decides
what that outcome is allowed to mean. ``Confirmed`` means the other region
reproduced the KPI fingerprint and the required variant still shows a
material regression. It does not mean the root-cause hypothesis is proven.

``Inconclusive`` always carries follow-up tasks. The AI review extension is
not called from this module.
"""

from __future__ import annotations

from fts.domain.package import FollowUpTask, Verdict

REPRODUCE_TASK = FollowUpTask(
    task_id="followup-reproduce",
    summary=(
        "Re-run model A and model B with the seed, scenario parameters, "
        "simulator version, container digest, and KPI rule version in this package. "
        "Do not substitute a different scene."
    ),
    kind="reproduce",
    recommended_test_id=None,
)

VARIANT_TASK = FollowUpTask(
    task_id="followup-variant-pedestrian-speed",
    summary=(
        "Run recommended test variant-pedestrian-speed-1.6. "
        "The overrides and seed are on that test object."
    ),
    kind="variant",
    recommended_test_id="variant-pedestrian-speed-1.6",
)


def verdict_after_discovery(*, material: bool) -> Verdict:
    if not material:
        return Verdict(
            state="No Material Regression",
            rationale=(
                "The pre-declared KPI rules found no material regression on this run. "
                "This is a rule outcome for the sealed inputs, not a measured fleet rate."
            ),
            follow_up_tasks=[],
        )
    return Verdict(
        state="Inconclusive",
        rationale=(
            "A material regression was observed at the discovering site. "
            "That is not a closed verdict: another region still has to reproduce "
            "the fingerprint, and the recommended variant has not been run. "
            "The root-cause hypothesis stays unconfirmed."
        ),
        follow_up_tasks=[REPRODUCE_TASK, VARIANT_TASK],
    )


def verdict_after_remote(*, reproduction_match: bool, variant_material: bool | None) -> Verdict:
    if not reproduction_match:
        return Verdict(
            state="Inconclusive",
            rationale=(
                "The receiving region reran the package and the KPI fingerprint did not match. "
                "Do not treat the failure as confirmed."
            ),
            follow_up_tasks=[
                FollowUpTask(
                    task_id="followup-investigate-mismatch",
                    summary=(
                        "Compare simulator version, container digest, seed, scenario parameter "
                        "hash, model checkpoint hashes, and KPI rule version with the package."
                    ),
                    kind="review",
                    recommended_test_id=None,
                )
            ],
        )
    if variant_material is None:
        return Verdict(
            state="Inconclusive",
            rationale=(
                "The original fingerprint matched, and the required variant has not been recorded."
            ),
            follow_up_tasks=[VARIANT_TASK],
        )
    if variant_material:
        return Verdict(
            state="Confirmed",
            rationale=(
                "The receiving region reproduced the KPI fingerprint from the package alone, "
                "and the pre-declared variant also showed a material regression under the same rules. "
                "Confirmed describes that regression, not the root-cause hypothesis. "
                "The hypothesis confidence is unchanged and is not a calibrated probability."
            ),
            follow_up_tasks=[],
        )
    return Verdict(
        state="Inconclusive",
        rationale=(
            "The original run reproduced, but the variant did not show a material regression. "
            "The failure is not yet isolated."
        ),
        follow_up_tasks=[
            FollowUpTask(
                task_id="followup-widen-sweep",
                summary=(
                    "Keep the original scene pinned and add another package-defined sweep "
                    "around pedestrian entry timing before treating the cause as isolated."
                ),
                kind="review",
                recommended_test_id=None,
            )
        ],
    )
