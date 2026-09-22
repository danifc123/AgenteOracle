from agente_oracle.tools.ia.saneamento import sanitizar_dado_sensivel, sanitizar_mensagens


class TestSanitizarDadoSensivel:
    def test_cpf_formatado_e_mascarado(self):
        texto = sanitizar_dado_sensivel("Tentei acessar com o CPF 123.456.789-00 e não deu certo.")
        assert "123.456.789-00" not in texto
        assert "[CPF]" in texto

    def test_cpf_sem_pontuacao_e_mascarado(self):
        texto = sanitizar_dado_sensivel("CPF cadastrado: 12345678900, sem acesso.")
        assert "12345678900" not in texto
        assert "[CPF]" in texto

    def test_email_e_mascarado(self):
        texto = sanitizar_dado_sensivel("Meu e-mail é joao.silva@conceitoagricola.com.br, não recebo nada.")
        assert "joao.silva@conceitoagricola.com.br" not in texto
        assert "[E-MAIL]" in texto

    def test_telefone_formatado_e_mascarado(self):
        texto = sanitizar_dado_sensivel("Pode ligar no (11) 91234-5678 se precisar.")
        assert "91234-5678" not in texto
        assert "[TELEFONE]" in texto

    def test_padrao_de_senha_e_mascarado(self):
        texto = sanitizar_dado_sensivel("Tentei com senha: MinhaSenha123 e não funcionou.")
        assert "MinhaSenha123" not in texto
        assert "[SENHA]" in texto

    def test_padrao_de_token_e_mascarado(self):
        texto = sanitizar_dado_sensivel("O token: abc-def-123 expirou ontem.")
        assert "abc-def-123" not in texto
        assert "[SENHA]" in texto

    def test_texto_normal_acentuado_fica_intacto(self):
        texto = "O sistema financeiro trava sempre que tento gerar o relatório de vendas do mês passado."
        assert sanitizar_dado_sensivel(texto) == texto

    def test_cpf_dentro_de_outra_palavra_nao_e_mascarado(self):
        # Não pode confundir um id de 11 dígitos colado em outro texto —
        # exige fronteira de palavra, como o CPF real teria.
        texto = sanitizar_dado_sensivel("pedidoID98765432109confirmado")
        assert texto == "pedidoID98765432109confirmado"


class TestSanitizarMensagens:
    def test_mascara_o_content_de_cada_mensagem(self):
        mensagens = [
            {"role": "system", "content": "Você é um triagista de service desk."},
            {"role": "user", "content": "Meu CPF é 123.456.789-00 e não consigo acessar."},
        ]

        saneadas = sanitizar_mensagens(mensagens)

        assert saneadas[0]["content"] == "Você é um triagista de service desk."
        assert "123.456.789-00" not in saneadas[1]["content"]
        assert "[CPF]" in saneadas[1]["content"]

    def test_preserva_o_role_de_cada_mensagem(self):
        mensagens = [{"role": "user", "content": "detalhe qualquer"}]
        saneadas = sanitizar_mensagens(mensagens)
        assert saneadas[0]["role"] == "user"

    def test_nao_modifica_a_lista_original(self):
        mensagens = [{"role": "user", "content": "CPF 123.456.789-00"}]
        sanitizar_mensagens(mensagens)
        assert mensagens[0]["content"] == "CPF 123.456.789-00"
