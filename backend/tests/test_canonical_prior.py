"""正藏优先：把 X 藏（卍續藏，几乎全是注疏）排到本经之后。

注疏天生赢过它所注的那部经——它把本经的词汇以更高的术语密度重述一遍，所以向量
检索和交叉编码器都更爱它。生产实测「五蕴是什么」召回四部心經注疏，本经缺席；
服务给 LLM 的五条上下文里平均 **2.24 条**是卍續藏。

2026-08-21 在生产管线上按档位扫过一遍（90 题，仅检索，基线臂精确重现了当天
夜间报告的 0.342 / 0.214，确认复现忠实）：

    档位      top5注疏   Hit@5    宽松Hit@5   MRR      段落题Hit@5
    基线       2.24      0.342     0.466      0.214     0.270
    ×0.70      1.08      0.384     0.534      0.221     0.317
    ×0.55      0.79      0.384     0.534      0.230     0.317
    ×0.25      0.54      0.384     0.534      0.230     0.317
    完全剔除    0.11      0.384     0.534      0.234     0.317

曲线在 ×0.55 饱和，此后到「完全剔除 X」都不再变化——真正起作用的只是「把 X 整体
排到非 X 之后」，档位数值本身不重要。归属题在每个档位都是 0.800，纹丝不动。

⚠️ 这些数字来自一把**几乎不问注疏**的尺子：89 个 gold 标题里只有 2 个是 X 藏
（古尊宿語錄、淨土聖賢錄）。所以它量得出「找不到本经」这种伤，量不出「读者想看
某家注疏却被降级」那种伤。默认关闭就是因为这个。
"""

import pytest

from app.services.rag_retrieval import _is_continued_canon, apply_canonical_prior


def _c(cbeta_id: str, score: float) -> dict:
    return {"cbeta_id": cbeta_id, "score": score, "text_id": 1, "juan_num": 1}


@pytest.fixture
def prior_on(monkeypatch):
    monkeypatch.setattr("app.services.rag_retrieval.settings.enable_canonical_prior", True)
    monkeypatch.setattr("app.services.rag_retrieval.settings.canonical_prior_penalty", 0.55)


class TestTierDetection:
    def test_recognises_the_continued_canon(self):
        assert _is_continued_canon(_c("X0123", 0.5)) is True

    @pytest.mark.parametrize("cid", ["T0251", "J0001", "B0001", "", "GA001"])
    def test_leaves_every_other_canon_alone(self, cid):
        assert _is_continued_canon(_c(cid, 0.5)) is False

    def test_survives_a_missing_cbeta_id(self):
        # LEFT JOIN, so cbeta_id can be None — must not raise.
        assert _is_continued_canon({"cbeta_id": None, "score": 0.5}) is False
        assert _is_continued_canon({"score": 0.5}) is False


class TestOrdering:
    def test_root_sutra_overtakes_a_higher_scoring_commentary(self, prior_on):
        # The production shape: commentary wins the rerank, root sutra sits below.
        results = [_c("X0523", 0.60), _c("T0251", 0.40)]
        assert [r["cbeta_id"] for r in apply_canonical_prior(results)] == ["T0251", "X0523"]

    def test_a_commanding_commentary_still_wins(self, prior_on):
        # 0.90 * 0.55 = 0.495 > 0.40 — the prior demotes, it does not exile.
        results = [_c("X0523", 0.90), _c("T0251", 0.40)]
        assert [r["cbeta_id"] for r in apply_canonical_prior(results)] == ["X0523", "T0251"]

    def test_nothing_is_dropped(self, prior_on):
        results = [_c("X1", 0.9), _c("X2", 0.8), _c("T1", 0.1)]
        assert len(apply_canonical_prior(results)) == 3

    def test_commentary_only_results_survive_in_rank_order(self, prior_on):
        # A question whose only real evidence is commentary must still get it.
        results = [_c("X1", 0.9), _c("X2", 0.5)]
        assert [r["cbeta_id"] for r in apply_canonical_prior(results)] == ["X1", "X2"]

    def test_ties_keep_the_reranker_order(self, prior_on):
        results = [_c("T0002", 0.5), _c("T0001", 0.5)]
        assert [r["cbeta_id"] for r in apply_canonical_prior(results)] == ["T0002", "T0001"]

    def test_does_not_rewrite_the_score_shown_to_the_reader(self, prior_on):
        # score rides out to the client on every ChatSource; a penalised value
        # there would misreport similarity.
        results = [_c("X0523", 0.60), _c("T0251", 0.40)]
        by_id = {r["cbeta_id"]: r["score"] for r in apply_canonical_prior(results)}
        assert by_id == {"X0523": 0.60, "T0251": 0.40}


class TestDisabledByDefault:
    def test_off_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.rag_retrieval.settings.enable_canonical_prior", False
        )
        results = [_c("X0523", 0.60), _c("T0251", 0.40)]
        assert apply_canonical_prior(results) is results

    def test_ships_off(self):
        from app.config import Settings

        assert Settings.model_fields["enable_canonical_prior"].default is False


class TestMasterPersonaCarveOut:
    """人格模式下不许应用先验——那份语料是特意选的，而且常常本身就是 X 藏。"""

    def test_scoped_retrieval_is_left_alone(self, prior_on):
        # 古尊宿語錄 is an X text and is exactly what a Chan master's corpus is.
        results = [_c("X1315", 0.60), _c("T0251", 0.40)]
        assert apply_canonical_prior(results, scoped=True) is results

    def test_unscoped_is_still_reordered(self, prior_on):
        results = [_c("X1315", 0.60), _c("T0251", 0.40)]
        got = apply_canonical_prior(results, scoped=False)
        assert [r["cbeta_id"] for r in got] == ["T0251", "X1315"]


class TestTheShapeItExistsFor:
    """生产形状：15 条候选里注疏霸榜，本经在第 6 位——它必须挤进前 5。

    这条用例才是先验的价值主张。上面多数断言是**不变量**（不丢行、不改分、
    平手保序），先验不生效时它们照样成立；把实现改成空操作，只有这里和
    TestOrdering 里那两条会红。
    """

    def _pool(self):
        # Commentary sweeps the rerank; 心經 loses the cosine race to its own
        # 注疏 and lands 6th — exactly the 「五蕴是什么」 failure.
        pool = [_c(f"X{i:04d}", 0.90 - i * 0.01) for i in range(5)]
        pool.append(_c("T0251", 0.80))
        pool += [_c(f"X{i:04d}", 0.70 - i * 0.01) for i in range(5, 14)]
        return pool

    def test_root_sutra_misses_the_cut_without_the_prior(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.rag_retrieval.settings.enable_canonical_prior", False
        )
        served = apply_canonical_prior(self._pool())[:5]
        assert "T0251" not in [r["cbeta_id"] for r in served]

    def test_root_sutra_takes_a_served_slot_with_it(self, prior_on):
        served = apply_canonical_prior(self._pool())[:5]
        assert served[0]["cbeta_id"] == "T0251"
        # And commentary is not exiled — it still fills the rest.
        assert sum(1 for r in served if r["cbeta_id"].startswith("X")) == 4
