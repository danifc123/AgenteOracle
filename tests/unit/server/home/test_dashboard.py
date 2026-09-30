from agente_oracle.server.home.dashboard import _catalogo_unificado, _formato_valido, _layout_visivel


def _item(widget_id: str, tamanho: str = "pequeno") -> dict:
    return {"id": widget_id, "tamanho": tamanho}


class TestCatalogoUnificado:
    def test_ids_de_cada_modulo_saem_prefixados_pelo_modulo_de_origem(self):
        catalogo = _catalogo_unificado()

        assert "ti:chamados_total" in catalogo
        assert "financeiro:saldo_projetado" in catalogo
        assert "rh:analise_candidato" in catalogo

    def test_entrada_traz_o_modulo_de_origem_e_a_definicao(self):
        modulo, definicao = _catalogo_unificado()["financeiro:faturamento_total"]

        assert modulo == "financeiro"
        assert definicao.exige_dev is False

    def test_widget_comum_sai_namespaced_como_comum_e_sem_modulo_de_origem(self):
        modulo, definicao = _catalogo_unificado()["comum:central_suporte"]

        assert modulo is None
        assert definicao.exige_dev is False

    def test_atalhos_que_antes_eram_fixos_agora_estao_no_catalogo(self):
        catalogo = _catalogo_unificado()

        assert "ti:seguranca" in catalogo
        assert "ti:auditoria_chamados" in catalogo
        assert "financeiro:criar_relatorio" in catalogo
        assert "comum:usuarios" in catalogo


class TestLayoutVisivel:
    def test_financeiro_so_ve_widgets_de_financeiro(self):
        widgets = [_item("financeiro:saldo_projetado"), _item("ti:chamados_total")]

        resultado = _layout_visivel(widgets, papeis_usuario=["financeiro"])

        assert resultado == [_item("financeiro:saldo_projetado")]

    def test_ti_so_ve_widgets_de_ti(self):
        widgets = [_item("financeiro:saldo_projetado"), _item("ti:chamados_total")]

        resultado = _layout_visivel(widgets, papeis_usuario=["ti_admin"])

        assert resultado == [_item("ti:chamados_total")]

    def test_usuario_com_os_dois_papeis_ve_os_dois_catalogos_juntos(self):
        widgets = [_item("financeiro:saldo_projetado"), _item("ti:chamados_total")]

        resultado = _layout_visivel(widgets, papeis_usuario=["financeiro", "ti_admin"])

        assert resultado == widgets

    def test_usuario_sem_nenhum_papel_liberado_nao_ve_nada(self):
        widgets = [_item("financeiro:saldo_projetado"), _item("ti:chamados_total")]

        assert _layout_visivel(widgets, papeis_usuario=["rh"]) == []

    def test_desenvolvedor_ve_widgets_que_exigem_dev(self):
        widgets = [_item("ti:ia_tokens_hoje")]

        assert _layout_visivel(widgets, papeis_usuario=["desenvolvedor"]) == widgets

    def test_nao_desenvolvedor_perde_widgets_que_exigem_dev_mesmo_tendo_acesso_ao_modulo(self):
        widgets = [_item("ti:chamados_total"), _item("ti:ia_tokens_hoje")]

        resultado = _layout_visivel(widgets, papeis_usuario=["ti_admin"])

        assert resultado == [_item("ti:chamados_total")]

    def test_id_desconhecido_do_catalogo_e_descartado(self):
        widgets = [_item("ti:chamados_total"), _item("ti:widget_que_nao_existe_mais")]

        resultado = _layout_visivel(widgets, papeis_usuario=["desenvolvedor"])

        assert resultado == [_item("ti:chamados_total")]

    def test_lista_vazia_devolve_lista_vazia(self):
        assert _layout_visivel([], papeis_usuario=["desenvolvedor"]) == []

    def test_dedup_por_id_mantem_o_primeiro_tamanho_visto(self):
        widgets = [_item("ti:chamados_total", "grande"), _item("ti:chamados_total", "pequeno")]

        resultado = _layout_visivel(widgets, papeis_usuario=["desenvolvedor"])

        assert resultado == [_item("ti:chamados_total", "grande")]

    def test_tamanho_ausente_cai_no_padrao_do_catalogo(self):
        widgets = [{"id": "ti:chamados_por_status"}]

        resultado = _layout_visivel(widgets, papeis_usuario=["desenvolvedor"])

        assert resultado == [_item("ti:chamados_por_status", "grande")]

    def test_tamanho_invalido_cai_no_padrao_do_catalogo(self):
        widgets = [{"id": "financeiro:saldo_projetado", "tamanho": "gigante"}]

        resultado = _layout_visivel(widgets, papeis_usuario=["financeiro"])

        assert resultado == [_item("financeiro:saldo_projetado", "pequeno")]

    def test_item_sem_id_reconhecido_e_ignorado(self):
        assert _layout_visivel([{"tamanho": "grande"}], papeis_usuario=["desenvolvedor"]) == []

    def test_widget_comum_aparece_pra_qualquer_papel_sem_nenhum_modulo_em_comum(self):
        widgets = [_item("comum:central_suporte")]

        assert _layout_visivel(widgets, papeis_usuario=["rh"]) == widgets

    def test_widget_comum_aparece_ate_pra_quem_nao_tem_papel_nenhum(self):
        widgets = [_item("comum:central_suporte")]

        assert _layout_visivel(widgets, papeis_usuario=[]) == widgets

    def test_widget_comum_que_exige_administrador_some_pra_quem_nao_e_administrador(self):
        widgets = [_item("comum:usuarios")]

        assert _layout_visivel(widgets, papeis_usuario=["financeiro"]) == []

    def test_widget_comum_que_exige_administrador_aparece_pra_qualquer_administrador(self):
        widgets = [_item("comum:usuarios")]

        assert _layout_visivel(widgets, papeis_usuario=["rh_admin"]) == widgets

    def test_atalho_de_rh_segue_o_mesmo_filtro_de_modulo_dos_indicadores(self):
        widgets = [_item("rh:analise_candidato"), _item("ti:chamados_total")]

        resultado = _layout_visivel(widgets, papeis_usuario=["rh"])

        assert resultado == [_item("rh:analise_candidato")]


class TestFormatoValido:
    def test_lista_de_objetos_com_id_e_valida(self):
        assert _formato_valido([{"id": "ti:chamados_total"}]) is True

    def test_lista_vazia_e_valida(self):
        assert _formato_valido([]) is True

    def test_item_sem_id_e_invalido(self):
        assert _formato_valido([{"tamanho": "grande"}]) is False

    def test_valor_que_nao_e_lista_e_invalido(self):
        assert _formato_valido({"id": "ti:chamados_total"}) is False
        assert _formato_valido(None) is False
