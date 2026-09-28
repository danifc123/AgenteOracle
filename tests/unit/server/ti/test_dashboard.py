from agente_oracle.server.ti.dashboard import _CATALOGO, _LAYOUT_PADRAO, _layout_visivel


def _item(widget_id: str, tamanho: str = "pequeno") -> dict:
    return {"id": widget_id, "tamanho": tamanho}


class TestLayoutVisivel:
    def test_desenvolvedor_ve_tudo_na_ordem_recebida(self):
        widgets = [_item("chamados_total"), _item("ia_tokens_hoje"), _item("chamados_por_status", "grande")]

        assert _layout_visivel(widgets, eh_dev=True) == widgets

    def test_nao_desenvolvedor_perde_os_ids_que_exigem_dev(self):
        widgets = [
            _item("chamados_total"),
            _item("ia_tokens_hoje"),
            _item("chamados_por_status"),
            _item("ia_chamados_escalados"),
        ]

        resultado = _layout_visivel(widgets, eh_dev=False)

        assert resultado == [_item("chamados_total"), _item("chamados_por_status")]

    def test_id_desconhecido_do_catalogo_e_descartado_mesmo_para_desenvolvedor(self):
        widgets = [_item("chamados_total"), _item("widget_que_nao_existe_mais")]

        assert _layout_visivel(widgets, eh_dev=True) == [_item("chamados_total")]

    def test_lista_vazia_devolve_lista_vazia(self):
        assert _layout_visivel([], eh_dev=True) == []

    def test_dedup_por_id_mantem_o_primeiro_tamanho_visto(self):
        widgets = [_item("chamados_total", "grande"), _item("chamados_total", "pequeno")]

        assert _layout_visivel(widgets, eh_dev=True) == [_item("chamados_total", "grande")]

    def test_tamanho_ausente_cai_no_padrao_do_catalogo(self):
        widgets = [{"id": "chamados_por_status"}]

        assert _layout_visivel(widgets, eh_dev=True) == [_item("chamados_por_status", "grande")]

    def test_tamanho_invalido_cai_no_padrao_do_catalogo(self):
        widgets = [{"id": "chamados_total", "tamanho": "gigante"}]

        assert _layout_visivel(widgets, eh_dev=True) == [_item("chamados_total", "pequeno")]

    def test_item_sem_id_reconhecido_e_ignorado(self):
        assert _layout_visivel([{"tamanho": "grande"}], eh_dev=True) == []


class TestCatalogoEPadrao:
    def test_todo_id_do_layout_padrao_existe_no_catalogo(self):
        assert all(item["id"] in _CATALOGO for item in _LAYOUT_PADRAO)

    def test_layout_padrao_sem_duplicata(self):
        ids = [item["id"] for item in _LAYOUT_PADRAO]
        assert len(ids) == len(set(ids))

    def test_layout_padrao_so_usa_tamanhos_validos(self):
        assert all(item["tamanho"] in {"pequeno", "grande"} for item in _LAYOUT_PADRAO)

    def test_seguranca_achados_ativos_nao_exige_desenvolvedor(self):
        assert _CATALOGO["seguranca_achados_ativos"].exige_dev is False
