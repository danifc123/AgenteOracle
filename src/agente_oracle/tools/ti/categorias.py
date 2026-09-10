"""211 categorias reais de chamado do GLPI (árvore "Tecnologia da
Informação" + "Processos"/"Projetos"), levantadas via export CSV da tela
Configuração > Listas suspensas > Categorias ITIL em 2026-09, confirmadas
completas com o responsável do GLPI da empresa (buracos de ID restantes
são categoria deletada ou de outro departamento, não TI).

`nome` é o "nome completo" do GLPI (caminho da árvore, ex: "Tecnologia da
Informação > Segurança da Informação > Firewall (Regras de Segurança) >
Relatar problema") — é esse texto que `agent/ti/roteamento_chamado.py`
usa pra comparar contra o conteúdo do chamado via embedding, então quanto
mais descritivo, melhor a comparação.

`area` vem do grupo GLPI dono de cada categoria (`category.group`, já
confirmado contra a API real): "TI > Infraestrutura de TI" -> infra,
"TI > Sistemas" -> sistemas, "Processos e Projetos" -> processos.

Dado puro, sem I/O — mesmo espírito de `tools/ti/tecnicos.py`: muda raro
o bastante pra "editar código, dar deploy" ser aceitável."""

from dataclasses import dataclass

from agente_oracle.tools.ti.glpi import AreaChamado


@dataclass(frozen=True)
class CategoriaGlpi:
    id: int
    nome: str
    area: AreaChamado


CATEGORIAS: tuple[CategoriaGlpi, ...] = (
    CategoriaGlpi(173, "Tecnologia da Informação > Meu Computador e Periféricos", "infra"),
    CategoriaGlpi(
        174, "Tecnologia da Informação > Meu Computador e Periféricos > Hardware e Componentes", "infra"
    ),
    CategoriaGlpi(
        175,
        "Tecnologia da Informação > Meu Computador e Periféricos > Hardware e Componentes > Solicitar novo equipamento ou componente (notebook, monitor, etc.)",
        "infra",
    ),
    CategoriaGlpi(
        176,
        "Tecnologia da Informação > Meu Computador e Periféricos > Hardware e Componentes > Substituição de componentes ou cabos danificados",
        "infra",
    ),
    CategoriaGlpi(
        177,
        "Tecnologia da Informação > Meu Computador e Periféricos > Hardware e Componentes > Realocação de equipamentos",
        "infra",
    ),
    CategoriaGlpi(
        178,
        "Tecnologia da Informação > Meu Computador e Periféricos > Hardware e Componentes > Solicitar empréstimo de notebook",
        "infra",
    ),
    CategoriaGlpi(
        179,
        "Tecnologia da Informação > Meu Computador e Periféricos > Hardware e Componentes > Relatar problema de Hardware",
        "infra",
    ),
    CategoriaGlpi(
        180,
        "Tecnologia da Informação > Meu Computador e Periféricos > Software e Sistema Operacional",
        "infra",
    ),
    CategoriaGlpi(
        181,
        "Tecnologia da Informação > Meu Computador e Periféricos > Software e Sistema Operacional > Gerenciamento de Software (Instalar/Remover)",
        "infra",
    ),
    CategoriaGlpi(
        182,
        "Tecnologia da Informação > Meu Computador e Periféricos > Software e Sistema Operacional > Configurações e Ajustes (Sistema, Periféricos)",
        "infra",
    ),
    CategoriaGlpi(
        183,
        "Tecnologia da Informação > Meu Computador e Periféricos > Software e Sistema Operacional > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        184,
        "Tecnologia da Informação > Meu Computador e Periféricos > Software e Sistema Operacional > Relatar problema de Software/Sistema",
        "infra",
    ),
    CategoriaGlpi(
        185, "Tecnologia da Informação > Meu Computador e Periféricos > Impressoras e Scanners", "infra"
    ),
    CategoriaGlpi(
        186,
        "Tecnologia da Informação > Meu Computador e Periféricos > Impressoras e Scanners > Instalação e Configuração",
        "infra",
    ),
    CategoriaGlpi(
        187,
        "Tecnologia da Informação > Meu Computador e Periféricos > Impressoras e Scanners > Solicitação de Suprimentos (Toner, Folhas)",
        "infra",
    ),
    CategoriaGlpi(
        188,
        "Tecnologia da Informação > Meu Computador e Periféricos > Impressoras e Scanners > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        189,
        "Tecnologia da Informação > Meu Computador e Periféricos > Impressoras e Scanners > Relatar problema",
        "infra",
    ),
    CategoriaGlpi(190, "Tecnologia da Informação > Contas e Acessos", "infra"),
    CategoriaGlpi(
        191, "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos", "infra"
    ),
    CategoriaGlpi(
        192,
        "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos > Criação de Acesso",
        "infra",
    ),
    CategoriaGlpi(
        193,
        "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos > Alteração de Acesso",
        "infra",
    ),
    CategoriaGlpi(
        194,
        "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos > Adicionar/remover usuário em grupo de e-mail",
        "infra",
    ),
    CategoriaGlpi(
        195,
        "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos > Conceder permissão em pasta (Sharepoint)",
        "infra",
    ),
    CategoriaGlpi(
        196,
        "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos > Criar acesso a pasta de rede (Sharepoint)",
        "infra",
    ),
    CategoriaGlpi(
        197,
        "Tecnologia da Informação > Contas e Acessos > Acessos a Sistemas, Pastas e Grupos > Relatar problema de acesso",
        "infra",
    ),
    CategoriaGlpi(198, "Tecnologia da Informação > Contas e Acessos > Acesso Remoto (VPN)", "infra"),
    CategoriaGlpi(
        199, "Tecnologia da Informação > Contas e Acessos > Acesso Remoto (VPN) > Configurar acesso", "infra"
    ),
    CategoriaGlpi(200, "Tecnologia da Informação > Contas e Acessos > Acesso Remoto (VPN) > Dúvida", "infra"),
    CategoriaGlpi(
        201, "Tecnologia da Informação > Contas e Acessos > Acesso Remoto (VPN) > Relatar problema", "infra"
    ),
    CategoriaGlpi(202, "Tecnologia da Informação > Comunicação e Colaboração", "infra"),
    CategoriaGlpi(203, "Tecnologia da Informação > Comunicação e Colaboração > E-mail", "infra"),
    CategoriaGlpi(
        204,
        "Tecnologia da Informação > Comunicação e Colaboração > E-mail > Criação de conta ou grupo de e-mail",
        "infra",
    ),
    CategoriaGlpi(
        205,
        "Tecnologia da Informação > Comunicação e Colaboração > E-mail > Configurar (assinatura, celular, etc.)",
        "infra",
    ),
    CategoriaGlpi(
        206,
        "Tecnologia da Informação > Comunicação e Colaboração > E-mail > Solicitar Backup de e-mail",
        "infra",
    ),
    CategoriaGlpi(
        207, "Tecnologia da Informação > Comunicação e Colaboração > E-mail > Bloquear remetente", "infra"
    ),
    CategoriaGlpi(208, "Tecnologia da Informação > Comunicação e Colaboração > E-mail > Dúvida", "infra"),
    CategoriaGlpi(
        209, "Tecnologia da Informação > Comunicação e Colaboração > E-mail > Relatar problema", "infra"
    ),
    CategoriaGlpi(210, "Tecnologia da Informação > Comunicação e Colaboração > Telefonia", "infra"),
    CategoriaGlpi(
        211,
        "Tecnologia da Informação > Comunicação e Colaboração > Telefonia > Instalação ou solicitação de aparelho/chip (Fixo e Móvel)",
        "infra",
    ),
    CategoriaGlpi(
        212,
        "Tecnologia da Informação > Comunicação e Colaboração > Telefonia > Configurações e habilitações (Roaming, MDM, etc.)",
        "infra",
    ),
    CategoriaGlpi(
        213, "Tecnologia da Informação > Comunicação e Colaboração > Telefonia > Backup WhatsApp", "infra"
    ),
    CategoriaGlpi(
        214,
        "Tecnologia da Informação > Comunicação e Colaboração > Telefonia > Dúvida (Fixa, Móvel, MDM)",
        "infra",
    ),
    CategoriaGlpi(
        215,
        "Tecnologia da Informação > Comunicação e Colaboração > Telefonia > Relatar problema (Fixa, Móvel, MDM)",
        "infra",
    ),
    CategoriaGlpi(216, "Tecnologia da Informação > Comunicação e Colaboração > Videoconferência", "infra"),
    CategoriaGlpi(
        217,
        "Tecnologia da Informação > Comunicação e Colaboração > Videoconferência > Instalação de aparelho",
        "infra",
    ),
    CategoriaGlpi(
        218,
        "Tecnologia da Informação > Comunicação e Colaboração > Videoconferência > Criar/alterar sala virtual",
        "infra",
    ),
    CategoriaGlpi(
        219, "Tecnologia da Informação > Comunicação e Colaboração > Videoconferência > Dúvida", "infra"
    ),
    CategoriaGlpi(
        220,
        "Tecnologia da Informação > Comunicação e Colaboração > Videoconferência > Relatar problema",
        "infra",
    ),
    CategoriaGlpi(
        221,
        "Tecnologia da Informação > Comunicação e Colaboração > Arquivos e Pastas de Rede (Onedrive/Sharepoint)",
        "infra",
    ),
    CategoriaGlpi(
        222,
        "Tecnologia da Informação > Comunicação e Colaboração > Arquivos e Pastas de Rede (Onedrive/Sharepoint) > Configurar sincronização",
        "infra",
    ),
    CategoriaGlpi(
        223,
        "Tecnologia da Informação > Comunicação e Colaboração > Arquivos e Pastas de Rede (Onedrive/Sharepoint) > Automação (Sharepoint)",
        "infra",
    ),
    CategoriaGlpi(
        224,
        "Tecnologia da Informação > Comunicação e Colaboração > Arquivos e Pastas de Rede (Onedrive/Sharepoint) > Dúvida (Onedrive/Sharepoint)",
        "infra",
    ),
    CategoriaGlpi(
        225,
        "Tecnologia da Informação > Comunicação e Colaboração > Arquivos e Pastas de Rede (Onedrive/Sharepoint) > Relatar problema (Sincronização, acesso, etc.)",
        "infra",
    ),
    CategoriaGlpi(226, "Tecnologia da Informação > Rede e Internet", "infra"),
    CategoriaGlpi(227, "Tecnologia da Informação > Rede e Internet > Conectividade", "infra"),
    CategoriaGlpi(
        228,
        "Tecnologia da Informação > Rede e Internet > Conectividade > Instalar ponto de rede ou Wi-Fi",
        "infra",
    ),
    CategoriaGlpi(229, "Tecnologia da Informação > Rede e Internet > Conectividade > Dúvida", "infra"),
    CategoriaGlpi(
        230,
        "Tecnologia da Informação > Rede e Internet > Conectividade > Relatar problema de conectividade (Internet, Rede, Wi-Fi)",
        "infra",
    ),
    CategoriaGlpi(231, "Tecnologia da Informação > Rede e Internet > Acesso a Sites e Aplicações", "infra"),
    CategoriaGlpi(
        232,
        "Tecnologia da Informação > Rede e Internet > Acesso a Sites e Aplicações > Solicitar liberação de site/aplicação",
        "infra",
    ),
    CategoriaGlpi(
        233,
        "Tecnologia da Informação > Rede e Internet > Acesso a Sites e Aplicações > Relatar problema de acesso (Site lento, erro, bloqueio indevido)",
        "infra",
    ),
    CategoriaGlpi(234, "Tecnologia da Informação > Segurança da Informação", "infra"),
    CategoriaGlpi(
        235, "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint", "infra"
    ),
    CategoriaGlpi(
        236,
        "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint > Instalação de Antivírus",
        "infra",
    ),
    CategoriaGlpi(
        237,
        "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint > Solicitar desbloqueio de periférico",
        "infra",
    ),
    CategoriaGlpi(
        238,
        "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        239,
        "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint > Relatar aplicativo bloqueado",
        "infra",
    ),
    CategoriaGlpi(
        240,
        "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint > Relatar ameaça (Phishing, Ransomware, Vírus)",
        "infra",
    ),
    CategoriaGlpi(
        241,
        "Tecnologia da Informação > Segurança da Informação > Antivírus e Proteção de EndPoint > Relatar outro problema",
        "infra",
    ),
    CategoriaGlpi(
        242, "Tecnologia da Informação > Segurança da Informação > Firewall (Regras de Segurança)", "infra"
    ),
    CategoriaGlpi(
        243,
        "Tecnologia da Informação > Segurança da Informação > Firewall (Regras de Segurança) > Liberar/Bloquear IP ou Porta",
        "infra",
    ),
    CategoriaGlpi(
        244,
        "Tecnologia da Informação > Segurança da Informação > Firewall (Regras de Segurança) > Criar/Alterar/Remover NAT",
        "infra",
    ),
    CategoriaGlpi(
        245,
        "Tecnologia da Informação > Segurança da Informação > Firewall (Regras de Segurança) > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        246,
        "Tecnologia da Informação > Segurança da Informação > Firewall (Regras de Segurança) > Relatar problema",
        "infra",
    ),
    CategoriaGlpi(247, "Tecnologia da Informação > Sistemas de Negócio", "sistemas"),
    CategoriaGlpi(248, "Tecnologia da Informação > Sistemas de Negócio > Bonzay Ponto", "sistemas"),
    CategoriaGlpi(
        249, "Tecnologia da Informação > Sistemas de Negócio > Bonzay Ponto > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        250,
        "Tecnologia da Informação > Sistemas de Negócio > Bonzay Ponto > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        251,
        "Tecnologia da Informação > Sistemas de Negócio > Bonzay Ponto > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(252, "Tecnologia da Informação > Sistemas de Negócio > Bonzay Ponto > Dúvida", "sistemas"),
    CategoriaGlpi(
        253, "Tecnologia da Informação > Sistemas de Negócio > Bonzay Ponto > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(254, "Tecnologia da Informação > Sistemas de Negócio > Businessmap", "sistemas"),
    CategoriaGlpi(
        255, "Tecnologia da Informação > Sistemas de Negócio > Businessmap > Integração", "sistemas"
    ),
    CategoriaGlpi(
        256,
        "Tecnologia da Informação > Sistemas de Negócio > Businessmap > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        257, "Tecnologia da Informação > Sistemas de Negócio > Businessmap > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(258, "Tecnologia da Informação > Sistemas de Negócio > Clover CRM", "sistemas"),
    CategoriaGlpi(
        259, "Tecnologia da Informação > Sistemas de Negócio > Clover CRM > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        260,
        "Tecnologia da Informação > Sistemas de Negócio > Clover CRM > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        261,
        "Tecnologia da Informação > Sistemas de Negócio > Clover CRM > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(262, "Tecnologia da Informação > Sistemas de Negócio > Clover CRM > Dúvida", "sistemas"),
    CategoriaGlpi(
        263, "Tecnologia da Informação > Sistemas de Negócio > Clover CRM > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(264, "Tecnologia da Informação > Sistemas de Negócio > GLPI", "sistemas"),
    CategoriaGlpi(
        265, "Tecnologia da Informação > Sistemas de Negócio > GLPI > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        266,
        "Tecnologia da Informação > Sistemas de Negócio > GLPI > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        267,
        "Tecnologia da Informação > Sistemas de Negócio > GLPI > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(268, "Tecnologia da Informação > Sistemas de Negócio > GLPI > Dúvida", "sistemas"),
    CategoriaGlpi(269, "Tecnologia da Informação > Sistemas de Negócio > GLPI > Relatar Erro", "sistemas"),
    CategoriaGlpi(270, "Tecnologia da Informação > Sistemas de Negócio > Integrações", "sistemas"),
    CategoriaGlpi(
        271, "Tecnologia da Informação > Sistemas de Negócio > Integrações > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        272,
        "Tecnologia da Informação > Sistemas de Negócio > Integrações > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        273,
        "Tecnologia da Informação > Sistemas de Negócio > Integrações > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(274, "Tecnologia da Informação > Sistemas de Negócio > Integrações > Dúvida", "sistemas"),
    CategoriaGlpi(
        275, "Tecnologia da Informação > Sistemas de Negócio > Integrações > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(276, "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila)", "sistemas"),
    CategoriaGlpi(
        277,
        "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila) > Permissão de Acesso",
        "sistemas",
    ),
    CategoriaGlpi(
        278,
        "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila) > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        279,
        "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila) > Renovação de Certificado",
        "sistemas",
    ),
    CategoriaGlpi(
        280,
        "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila) > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(
        281, "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila) > Dúvida", "sistemas"
    ),
    CategoriaGlpi(
        282,
        "Tecnologia da Informação > Sistemas de Negócio > Motor Fiscal (Compila) > Relatar Erro",
        "sistemas",
    ),
    CategoriaGlpi(283, "Tecnologia da Informação > Sistemas de Negócio > PIMS MC", "sistemas"),
    CategoriaGlpi(
        284, "Tecnologia da Informação > Sistemas de Negócio > PIMS MC > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        285,
        "Tecnologia da Informação > Sistemas de Negócio > PIMS MC > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        286,
        "Tecnologia da Informação > Sistemas de Negócio > PIMS MC > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(287, "Tecnologia da Informação > Sistemas de Negócio > PIMS MC > Dúvida", "sistemas"),
    CategoriaGlpi(288, "Tecnologia da Informação > Sistemas de Negócio > PIMS MC > Relatar Erro", "sistemas"),
    CategoriaGlpi(289, "Tecnologia da Informação > Sistemas de Negócio > Power B.I", "sistemas"),
    CategoriaGlpi(
        290, "Tecnologia da Informação > Sistemas de Negócio > Power B.I > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        291,
        "Tecnologia da Informação > Sistemas de Negócio > Power B.I > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        292,
        "Tecnologia da Informação > Sistemas de Negócio > Power B.I > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(293, "Tecnologia da Informação > Sistemas de Negócio > Power B.I > Dúvida", "sistemas"),
    CategoriaGlpi(
        294, "Tecnologia da Informação > Sistemas de Negócio > Power B.I > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(295, "Tecnologia da Informação > Sistemas de Negócio > Protheus", "sistemas"),
    CategoriaGlpi(
        296, "Tecnologia da Informação > Sistemas de Negócio > Protheus > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        297,
        "Tecnologia da Informação > Sistemas de Negócio > Protheus > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        298,
        "Tecnologia da Informação > Sistemas de Negócio > Protheus > Renovação de Certificado",
        "sistemas",
    ),
    CategoriaGlpi(
        299,
        "Tecnologia da Informação > Sistemas de Negócio > Protheus > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(300, "Tecnologia da Informação > Sistemas de Negócio > Protheus > Dúvida", "sistemas"),
    CategoriaGlpi(
        301, "Tecnologia da Informação > Sistemas de Negócio > Protheus > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(302, "Tecnologia da Informação > Sistemas de Negócio > Senior", "sistemas"),
    CategoriaGlpi(
        303, "Tecnologia da Informação > Sistemas de Negócio > Senior > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        304,
        "Tecnologia da Informação > Sistemas de Negócio > Senior > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        305,
        "Tecnologia da Informação > Sistemas de Negócio > Senior > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(306, "Tecnologia da Informação > Sistemas de Negócio > Senior > Dúvida", "sistemas"),
    CategoriaGlpi(307, "Tecnologia da Informação > Sistemas de Negócio > Senior > Relatar Erro", "sistemas"),
    CategoriaGlpi(308, "Tecnologia da Informação > Sistemas de Negócio > Siagri Agribusiness", "sistemas"),
    CategoriaGlpi(
        309,
        "Tecnologia da Informação > Sistemas de Negócio > Siagri Agribusiness > Permissão de Acesso",
        "sistemas",
    ),
    CategoriaGlpi(
        310,
        "Tecnologia da Informação > Sistemas de Negócio > Siagri Agribusiness > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        311,
        "Tecnologia da Informação > Sistemas de Negócio > Siagri Agribusiness > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(
        312, "Tecnologia da Informação > Sistemas de Negócio > Siagri Agribusiness > Dúvida", "sistemas"
    ),
    CategoriaGlpi(
        313, "Tecnologia da Informação > Sistemas de Negócio > Siagri Agribusiness > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(314, "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI)", "infra"),
    CategoriaGlpi(
        315, "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Servidores", "infra"
    ),
    CategoriaGlpi(
        316,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Servidores > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        317,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Servidores > Relatar problema de desempenho (CPU, Memória)",
        "infra",
    ),
    CategoriaGlpi(
        318,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Servidores > Relatar outro problema",
        "infra",
    ),
    CategoriaGlpi(
        319,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Máquina Virtual (VM)",
        "infra",
    ),
    CategoriaGlpi(
        320,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Máquina Virtual (VM) > Criar/Apagar VM",
        "infra",
    ),
    CategoriaGlpi(
        321,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Máquina Virtual (VM) > Alterar recursos de VM",
        "infra",
    ),
    CategoriaGlpi(
        322,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Máquina Virtual (VM) > Gerenciar Snapshot",
        "infra",
    ),
    CategoriaGlpi(
        323,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Máquina Virtual (VM) > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        324,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Máquina Virtual (VM) > Relatar problema",
        "infra",
    ),
    CategoriaGlpi(
        325,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Banco de Dados",
        "infra",
    ),
    CategoriaGlpi(
        326,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Banco de Dados > Criar usuário",
        "infra",
    ),
    CategoriaGlpi(
        327,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Banco de Dados > Replicar",
        "infra",
    ),
    CategoriaGlpi(
        328,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Banco de Dados > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        329,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Banco de Dados > Relatar problema",
        "infra",
    ),
    CategoriaGlpi(
        330,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Certificados Digitais",
        "infra",
    ),
    CategoriaGlpi(
        331,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Certificados Digitais > Instalação/Renovação",
        "infra",
    ),
    CategoriaGlpi(
        332,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Certificados Digitais > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        333,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Certificados Digitais > Relatar problema",
        "infra",
    ),
    CategoriaGlpi(
        334, "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > CFTV", "infra"
    ),
    CategoriaGlpi(
        335,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > CFTV > Instalação/Movimentação/Substituição de Câmera",
        "infra",
    ),
    CategoriaGlpi(
        336,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > CFTV > Configuração de Câmera",
        "infra",
    ),
    CategoriaGlpi(
        337,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > CFTV > Solicitação (Gravações, Usuário, Backup)",
        "infra",
    ),
    CategoriaGlpi(
        338,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > CFTV > Dúvida",
        "infra",
    ),
    CategoriaGlpi(
        339,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > CFTV > Relatar problema/Falha",
        "infra",
    ),
    CategoriaGlpi(
        340, "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Outros", "infra"
    ),
    CategoriaGlpi(
        341, "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > API", "infra"
    ),
    CategoriaGlpi(
        342, "Tecnologia da Informação > Comunicação e Colaboração > Telefonia > Operadora", "infra"
    ),
    CategoriaGlpi(384, "Tecnologia da Informação > Comunicação e Colaboração > Sharepoint", "infra"),
    CategoriaGlpi(
        386, "Tecnologia da Informação > Comunicação e Colaboração > Sharepoint > Relatar problema", "infra"
    ),
    CategoriaGlpi(
        387,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Banco de Dados > Permissões",
        "infra",
    ),
    CategoriaGlpi(
        388,
        "Tecnologia da Informação > Meu Computador e Periféricos > Software e Sistema Operacional > Wallpaper",
        "infra",
    ),
    CategoriaGlpi(390, "Processos", "processos"),
    CategoriaGlpi(391, "Processos > Mapeamento de processo", "processos"),
    CategoriaGlpi(392, "Processos > Revisão/melhoria de processo existente", "processos"),
    CategoriaGlpi(393, "Processos > Padronização", "processos"),
    CategoriaGlpi(394, "Processos > Automatização de processo", "processos"),
    CategoriaGlpi(395, "Processos > Diagnóstico de problemas", "processos"),
    CategoriaGlpi(396, "Processos > Outros", "processos"),
    CategoriaGlpi(398, "Projetos", "processos"),
    CategoriaGlpi(399, "Projetos > Implantação de sistema", "processos"),
    CategoriaGlpi(400, "Projetos > Melhoria de processo com alto impacto", "processos"),
    CategoriaGlpi(401, "Projetos > Atendimento regulatório/legal", "processos"),
    CategoriaGlpi(402, "Projetos > Inovação", "processos"),
    CategoriaGlpi(403, "Projetos > Estratégico", "processos"),
    CategoriaGlpi(404, "Projetos > Outros", "processos"),
    CategoriaGlpi(405, "Tecnologia da Informação > Sistemas de Negócio > Power B.I > Licença", "infra"),
    CategoriaGlpi(406, "Tecnologia da Informação > Microsoft 365", "infra"),
    CategoriaGlpi(407, "Tecnologia da Informação > Microsoft 365 > Integração Entra/Azure AD", "infra"),
    CategoriaGlpi(422, "Tecnologia da Informação > Sistemas de Negócio > Simple Agro", "sistemas"),
    CategoriaGlpi(
        423, "Tecnologia da Informação > Sistemas de Negócio > Simple Agro > Permissão de Acesso", "sistemas"
    ),
    CategoriaGlpi(
        424,
        "Tecnologia da Informação > Sistemas de Negócio > Simple Agro > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        425,
        "Tecnologia da Informação > Sistemas de Negócio > Simple Agro > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(426, "Tecnologia da Informação > Sistemas de Negócio > Simple Agro > Dúvida", "sistemas"),
    CategoriaGlpi(
        427, "Tecnologia da Informação > Sistemas de Negócio > Simple Agro > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(442, "Tecnologia da Informação > Sistemas de Negócio > eBarn (cotaí)", "sistemas"),
    CategoriaGlpi(
        443,
        "Tecnologia da Informação > Sistemas de Negócio > eBarn (cotaí) > Permissão de Acesso",
        "sistemas",
    ),
    CategoriaGlpi(
        444,
        "Tecnologia da Informação > Sistemas de Negócio > eBarn (cotaí) > Suporte Operacional (Cadastros, Ajustes de Parâmetros)",
        "sistemas",
    ),
    CategoriaGlpi(
        445,
        "Tecnologia da Informação > Sistemas de Negócio > eBarn (cotaí) > Solicitação de Melhoria/Mudança",
        "sistemas",
    ),
    CategoriaGlpi(446, "Tecnologia da Informação > Sistemas de Negócio > eBarn (cotaí) > Dúvida", "sistemas"),
    CategoriaGlpi(
        447, "Tecnologia da Informação > Sistemas de Negócio > eBarn (cotaí) > Relatar Erro", "sistemas"
    ),
    CategoriaGlpi(
        449,
        "Tecnologia da Informação > Meu Computador e Periféricos > Solicitação de Melhoria/Mudança",
        "infra",
    ),
    CategoriaGlpi(
        450,
        "Tecnologia da Informação > Infraestrutura e Datacenter (Uso Restrito/TI) > Solicitação de Melhoria/Mudança",
        "infra",
    ),
    CategoriaGlpi(
        451, "Tecnologia da Informação > Contas e Acessos > Solicitação de Melhoria/Mudança", "infra"
    ),
    CategoriaGlpi(
        452, "Tecnologia da Informação > Comunicação e Colaboração > Solicitação de Melhoria/Mudança", "infra"
    ),
    CategoriaGlpi(
        453, "Tecnologia da Informação > Rede e Internet > Solicitação de Melhoria/Mudança", "infra"
    ),
    CategoriaGlpi(
        454, "Tecnologia da Informação > Segurança da Informação > Solicitação de Melhoria/Mudança", "infra"
    ),
    CategoriaGlpi(
        473,
        "Tecnologia da Informação > Segurança da Informação > Firewall (Regras de Segurança) > Liberar/Bloquear Site",
        "infra",
    ),
    CategoriaGlpi(
        476,
        "Tecnologia da Informação > Comunicação e Colaboração > Arquivos e Pastas de Rede (Onedrive/Sharepoint) > Criar pasta",
        "infra",
    ),
)

AREA_POR_CATEGORIA_ID: dict[int, AreaChamado] = {categoria.id: categoria.area for categoria in CATEGORIAS}


def _eh_folha(categoria: CategoriaGlpi) -> bool:
    """Só uma folha de verdade pode ser escolhida como categoria nova de
    um chamado — um nó "pasta" da árvore (ex: "Tecnologia da Informação >
    Meu Computador e Periféricos" sozinho) não é selecionável no GLPI de
    verdade (confirmado pelos campos `is_incident_visible`/
    `is_request_visible` da API: pasta tem tudo `False`). Aproximação por
    profundidade do nome, já que nem toda linha levantada guardou esses
    campos de visibilidade originais: folha de Infra/Sistemas fica pelo
    menos 4 níveis abaixo da raiz "Tecnologia da Informação" (3 `" > "`);
    folha de Processos/Projetos fica só 1 nível abaixo de "Processos"/
    "Projetos" (1 `" > "`)."""
    minimo = 1 if categoria.area == "processos" else 3
    return categoria.nome.count(" > ") >= minimo


CATEGORIAS_ATRIBUIVEIS: tuple[CategoriaGlpi, ...] = tuple(
    categoria for categoria in CATEGORIAS if _eh_folha(categoria)
)
