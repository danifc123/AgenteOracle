import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { CampoNumerico } from '../../../../componentes/campo-numerico/campo-numerico';
import { ConfirmacaoDialog } from '../../../../componentes/confirmacao-dialog/confirmacao-dialog';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { FatiaRosca, GraficoRosca } from '../../../../componentes/grafico-rosca/grafico-rosca';
import { GraficoSerie, SerieGrafico } from '../../../../componentes/grafico-serie/grafico-serie';
import { MenuAcoes } from '../../../../componentes/menu-acoes/menu-acoes';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { Selo } from '../../../../componentes/selo/selo';
import { PassoTour, TourGuiado } from '../../../../componentes/tour-guiado/tour-guiado';
import {
  AlteracoesConfiguracoesTi,
  ConfiguracoesTi,
} from '../../../../servicos/configuracoes-ti/configuracoes-ti';
import { mensagemErro } from '../../../../servicos/mensagens-erro/mensagens-erro';
import { UsoIa } from '../../../../servicos/uso-ia/uso-ia';

export type TipoConexaoLlm = 'ollama' | 'openai_compativel';
export type EstiloApiLlm = 'chat_completions' | 'responses';

interface ProvedorLlm {
  id: number;
  nome: string;
  tipo_conexao: TipoConexaoLlm;
  base_url: string;
  api_key_configurada: boolean;
  projeto_id: string;
  modelo: string;
  estilo_api: EstiloApiLlm;
  preco_entrada_por_1k: number;
  preco_saida_por_1k: number;
  moeda: string;
  ativo: boolean;
  criado_em: string;
}

const OPCOES_TIPO_CONEXAO: OpcaoSelectBusca[] = [
  { valor: 'ollama', rotulo: 'Ollama' },
  { valor: 'openai_compativel', rotulo: 'Compatível com OpenAI' },
];

const OPCOES_ESTILO_API: OpcaoSelectBusca[] = [
  { valor: 'chat_completions', rotulo: 'Padrão (Chat Completions)' },
  { valor: 'responses', rotulo: 'Responses API — só se o provedor exigir' },
];

// Fechado nessas duas de propósito (pedido do Daniel, 2026-09-25) — antes
// era texto livre, e a conversão automática pra R$ (`custo_brl`, ver
// `uso-ia.ts`) só sabe fazer conta com "US$" exatamente; deixar digitar
// qualquer coisa quebraria essa conversão silenciosamente.
const OPCOES_MOEDA: OpcaoSelectBusca[] = [
  { valor: 'R$', rotulo: 'R$ — Real' },
  { valor: 'US$', rotulo: 'US$ — Dólar' },
];

const URL_PROVEDORES = `${MCP_API_BASE_URL}/api/ti/provedores-llm`;

// Consumo muda sozinho (poller de chamados a cada 5 min, chamadas reais
// do dia a dia) — sem isso, quem deixa essa tela aberta só vê o número
// congelado do momento em que entrou, precisando dar F5 pra atualizar.
const INTERVALO_ATUALIZACAO_USO_IA_MS = 30_000;

/** Tour guiado (`componentes/tour-guiado/`) de como cadastrar um provedor
 * — não é "o tour da OCI", é o tour do CADASTRO, que usa a OCI como
 * exemplo concreto pra ilustrar cada campo (poderia ser qualquer outro
 * provedor compatível com OpenAI). Só em campos SEMPRE presentes no
 * formulário, de propósito: o tour é passivo (não preenche nada sozinho),
 * então se um passo apontasse pra "Estilo de chamada" ou "Projeto" (só
 * existem com "Compatível com OpenAI" escolhido) e a pessoa ainda
 * estivesse no Ollama, esse passo não teria alvo. O passo do "Tipo de
 * conexão" já avisa que escolher "Compatível com OpenAI" revela os dois
 * campos extras, cada um com sua própria dica quando aparecer. */
const PASSOS_TOUR_CADASTRO: PassoTour[] = [
  {
    alvo: '[data-tour-alvo="nome"]',
    titulo: 'Nome',
    descricao: 'Um nome livre, só pra você identificar esse cadastro depois — ex: "OCI Generative AI — gpt-oss-120b".',
  },
  {
    alvo: '[data-tour-alvo="tipo-conexao"]',
    titulo: 'Tipo de conexão',
    descricao:
      'Escolha o formato que o provedor fala: "Ollama" pra Ollama local ou instalação própria, e "Compatível com OpenAI" pra qualquer serviço que fale a API da OpenAI — a OCI é um exemplo disso. Escolher "Compatível com OpenAI" revela dois campos a mais (Estilo de chamada e Projeto), cada um com sua própria dica quando aparecer.',
  },
  {
    alvo: '[data-tour-alvo="endereco"]',
    titulo: 'Endereço (URL base)',
    descricao:
      'O endereço base que o provedor informou na documentação — muda de provedor pra provedor. Exemplo real, da OCI Generative AI: https://inference.generativeai.<região>.oci.oraclecloud.com/openai/v1 (trocando <região> pela região da conta).',
  },
  {
    alvo: '[data-tour-alvo="modelo"]',
    titulo: 'Modelo',
    descricao:
      'O nome exato do modelo liberado pelo suporte Oracle — ex: openai.gpt-oss-120b, meta.llama-3.3-70b-instruct ou meta.llama-4-scout-17b-16e-instruct.',
  },
  {
    alvo: '[data-tour-alvo="chave-api"]',
    titulo: 'Chave de API',
    descricao:
      'A chave de API que o provedor te deu — no caso da OCI, por exemplo, vem de um projeto criado no console da Oracle. É secreta: depois de salva, nunca mais volta preenchida na tela, nem pra você.',
  },
  {
    alvo: '[data-tour-alvo="precos"]',
    titulo: 'Preço por 1.000 tokens e moeda',
    descricao:
      'Preço é opcional — pode deixar 0 por enquanto, e preencher depois quando o provedor informar o valor de verdade (ex: quando a Oracle mandar a tabela de preços da OCI). Moeda é só o prefixo mostrado na tela (ex: "R$"), sem conversão automática.',
  },
  {
    alvo: '[data-tour-alvo="criar-provedor"]',
    titulo: 'Pronto!',
    descricao: 'Depois de preencher tudo, é só clicar aqui pra criar o provedor.',
  },
];

/** Preço aceita vírgula ou ponto, sem teto nem limite de casas (o backend
 * usa `Decimal` — só a exibição na lista é que arredonda) — mesmo espírito
 * de `percentualValido` (`servicos/amostragem-chamados`), sem o teto de 100. */
function precoValido(texto: string): number | null {
  const limpo = texto.trim().replace(',', '.');
  return /^\d+(\.\d+)?$/.test(limpo) ? Number(limpo) : null;
}

/** Cores reais do design system (ver `styles.scss`) — o nome do provedor é
 * o nome cadastrado por quem usa, não um código fixo, então não dá pra
 * fixar cor por provedor conhecido: roda por essa lista, sempre na mesma
 * ordem em que os provedores aparecem. */
const CORES_RESERVA = ['#1b4332', '#e8871e', '#2f9e58', '#5b6b62', '#c96f12'];

function corDoProvedor(indice: number): string {
  return CORES_RESERVA[indice % CORES_RESERVA.length];
}

/** "dd/MM" — mais curto que a data ISO completa, cabe no eixo X do
 * gráfico sem precisar mexer em `GraficoSerie` (que hoje só sabe formatar
 * rótulo no formato "YYYY-MM", pensado pra série mensal financeira). */
function formatarDiaCurto(dataIso: string): string {
  const partes = dataIso.split('-');
  return partes.length === 3 ? `${partes[2]}/${partes[1]}` : dataIso;
}

/** `custo` é sempre o preço CADASTRADO HOJE (não congelado por chamada) —
 * ver `server/ti/uso_ia.py::_custo_e_moeda` no backend. Até 4 casas: preço
 * por 1k tokens costuma ser bem pequeno (ex: R$ 0,0100), 2 casas some o
 * valor real. Quando o cadastro é em US$ e a cotação do dia veio
 * (`custoBrl`), mostra a conversão ao lado — quem decide trocar de
 * provedor enxerga o gasto na mesma moeda que a empresa usa pra decidir,
 * sem misturar com o cálculo de custo em si (sempre na moeda original). */
function formatarCusto(custo: number, moeda: string, custoBrl: number | null): string {
  const valor = `${moeda} ${custo.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  if (custoBrl === null) {
    return valor;
  }
  const convertido = custoBrl.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  return `${valor} (≈ R$ ${convertido})`;
}

/** MÓDULO TI — TELA "IA" (`/ti/provedores`, só desenvolvedor)
 *
 * Junta em uma página só o que antes eram duas telas separadas
 * (`/ti/provedores` + `/ti/tokens`, 2026-09) — cadastro/ativação de LLM em
 * cima, consumo/custo embaixo, porque no fundo é a mesma pergunta ("qual
 * LLM eu uso, e quanto ele custa"). Ver `tools/ia/provedores_llm.py` no
 * backend pro cadastro em si.
 *
 * Cadastro: cada linha é UMA conexão + UM modelo, e só fala uma de duas
 * "linguagens" (`tipo_conexao`): Ollama nativo, ou qualquer serviço
 * compatível com a API da OpenAI (a OCI inclusa). Dentro da segunda,
 * `estilo_api` escolhe entre Chat Completions (a maioria dos modelos) e
 * Responses API (só quando o modelo exige — confirmado com o suporte
 * Oracle pro gpt-oss-120b). Preço é opcional pra qualquer um dos dois,
 * inclusive Ollama (que não tem custo real em dinheiro) — alimenta a
 * estimativa de custo mostrada mais abaixo, na mesma tela. Chave de API
 * nunca volta do backend depois de salva (só o booleano
 * `api_key_configurada`) — editar sem preencher o campo de novo mantém a
 * que já estava lá.
 *
 * Consumo: dois gráficos (`GraficoRosca`/`GraficoSerie`, já usados em
 * Estoque/Financeiro, nenhuma lib nova) — donut de consumo por provedor e
 * tendência diária — mais a tabela detalhada com abas "Geral"/"Por
 * usuário". O teto diário de tokens fica atrás da engrenagem no
 * cabeçalho, mesmo padrão que `chamados.html` já usa pras próprias
 * configurações.
 *
 * Só desenvolvedor acessa (rota protegida por `devGuard`, item do menu
 * escondido de quem não é desenvolvedor via `ItemMenu.soDev`) — o backend
 * também exige isso em cada rota que essa tela chama, então não é
 * proteção só de aparência. */
@Component({
  selector: 'app-provedores-llm',
  imports: [
    Botao,
    CampoNumerico,
    ConfirmacaoDialog,
    Dialog,
    EstadoVazio,
    GraficoRosca,
    GraficoSerie,
    MenuAcoes,
    ModuloHeader,
    SelectBusca,
    Selo,
    TourGuiado,
  ],
  templateUrl: './provedores.html',
  styleUrl: './provedores.scss',
})
export class ProvedoresLlm {
  private readonly http = inject(HttpClient);
  private readonly usoIa = inject(UsoIa);
  protected readonly configuracoes = inject(ConfiguracoesTi);

  // Cadastro: lista + diálogo de criar/editar + apagar
  provedores = signal<ProvedorLlm[]>([]);
  carregando = signal(true);
  erro = signal<string | null>(null);

  dialogAberto = signal(false);
  editando = signal<ProvedorLlm | null>(null);
  salvando = signal(false);
  erroForm = signal<string | null>(null);

  provedorParaApagar = signal<ProvedorLlm | null>(null);
  apagandoId = signal<number | null>(null);
  ativandoId = signal<number | null>(null);
  desativandoId = signal<number | null>(null);

  formNome = signal('');
  formTipoConexao = signal<TipoConexaoLlm>('ollama');
  formBaseUrl = signal('');
  formApiKey = signal('');
  formProjetoId = signal('');
  formModelo = signal('');
  formEstiloApi = signal<EstiloApiLlm>('chat_completions');
  formPrecoEntrada = signal('0');
  formPrecoSaida = signal('0');
  formMoeda = signal('R$');

  tourAberto = signal(false);
  protected readonly passosTourCadastro = PASSOS_TOUR_CADASTRO;

  protected readonly opcoesTipoConexao = OPCOES_TIPO_CONEXAO;
  protected readonly opcoesEstiloApi = OPCOES_ESTILO_API;
  protected readonly opcoesMoeda = OPCOES_MOEDA;

  protected readonly ehOpenAiCompativel = computed(() => this.formTipoConexao() === 'openai_compativel');

  protected readonly precoEntradaValido = computed(() => precoValido(this.formPrecoEntrada()));
  protected readonly precoSaidaValido = computed(() => precoValido(this.formPrecoSaida()));

  protected readonly tituloDialog = computed(() => {
    const provedor = this.editando();
    return provedor ? `Editar "${provedor.nome}"` : 'Novo provedor';
  });

  protected readonly mensagemConfirmacaoApagar = computed(() => {
    const provedor = this.provedorParaApagar();
    if (!provedor) {
      return '';
    }
    const aviso = provedor.ativo
      ? ' Ele está ativo agora — depois de apagado, o sistema volta a usar o Ollama padrão do .env.'
      : '';
    return `Apagar o provedor "${provedor.nome}"? Essa ação não pode ser desfeita.${aviso}`;
  });

  // Consumo: gráficos, tabela detalhada e teto diário de tokens
  protected readonly consumo = this.usoIa.consumo;
  protected readonly porUsuario = this.usoIa.porUsuario;
  protected readonly porDia = this.usoIa.porDia;
  protected readonly tokensHojePorDominio = this.usoIa.tokensHojePorDominio;

  /** "Geral" = por provedor/modelo (responde "o que está custando");
   * "usuario" = por pessoa (responde "quem está gastando"). */
  protected readonly abaAtiva = signal<'geral' | 'usuario'>('geral');

  protected readonly configuracoesAbertas = signal(false);
  protected readonly tetoTexto = signal('0');
  protected readonly salvandoTeto = signal(false);
  protected readonly erroTeto = signal<string | null>(null);

  protected readonly tokensHojeTotal = computed(() =>
    Object.values(this.tokensHojePorDominio()).reduce((total, valor) => total + valor, 0),
  );

  protected readonly fatiasProvedor = computed<FatiaRosca[]>(() => {
    const porProvedor = new Map<string, number>();
    for (const linha of this.consumo()) {
      porProvedor.set(linha.provedor, (porProvedor.get(linha.provedor) ?? 0) + linha.tokens_total);
    }
    return Array.from(porProvedor.entries()).map(([provedor, tokens], indice) => ({
      nome: provedor,
      valor: tokens,
      cor: corDoProvedor(indice),
    }));
  });

  protected readonly serieTokensPorDia = computed<SerieGrafico[]>(() => [
    {
      nome: 'Tokens',
      cor: '#1b4332',
      pontos: this.porDia().map((linha) => ({
        rotulo: formatarDiaCurto(linha.data),
        valor: linha.tokens_total,
      })),
    },
  ]);

  protected readonly tetoValido = computed<number | null>(() => {
    const numero = Number(this.tetoTexto());
    return Number.isInteger(numero) && numero >= 0 ? numero : null;
  });

  /** `null` = sem teto configurado (0), não mostra a barra de progresso. */
  protected readonly percentualTeto = computed<number | null>(() => {
    const teto = this.configuracoes.tetoTokensDiario();
    if (teto <= 0) {
      return null;
    }
    return Math.min(100, Math.round((this.tokensHojeTotal() / teto) * 100));
  });

  protected readonly tomTeto = computed<'ok' | 'atencao' | 'erro'>(() => {
    const percentual = this.percentualTeto();
    if (percentual === null) {
      return 'ok';
    }
    return percentual >= 100 ? 'erro' : percentual >= 80 ? 'atencao' : 'ok';
  });

  constructor() {
    this.carregarProvedores();
    this.usoIa.carregar();
    const intervalo = setInterval(() => this.usoIa.carregar(), INTERVALO_ATUALIZACAO_USO_IA_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(intervalo));
    this.configuracoes.carregar();
    // Semeia o rascunho do teto sempre que o valor real do servidor muda
    // (primeiro load, e depois de salvar) — mesmo espírito de
    // `iniciarRascunho` em `configuracoes-chamados.ts`.
    effect(() => this.tetoTexto.set(String(this.configuracoes.tetoTokensDiario())));
  }

  carregarProvedores(): void {
    this.carregando.set(true);
    this.erro.set(null);

    this.http.get<ProvedorLlm[]>(URL_PROVEDORES).subscribe({
      next: (provedores) => {
        this.provedores.set(provedores);
        this.carregando.set(false);
      },
      error: () => {
        this.erro.set('Não foi possível carregar os provedores.');
        this.carregando.set(false);
      },
    });
  }

  abrirDialogCriar(): void {
    this.editando.set(null);
    this.formNome.set('');
    this.formTipoConexao.set('ollama');
    this.formBaseUrl.set('');
    this.formApiKey.set('');
    this.formProjetoId.set('');
    this.formModelo.set('');
    this.formEstiloApi.set('chat_completions');
    this.formPrecoEntrada.set('0');
    this.formPrecoSaida.set('0');
    this.formMoeda.set('R$');
    this.erroForm.set(null);
    this.dialogAberto.set(true);
  }

  abrirDialogEditar(provedor: ProvedorLlm): void {
    this.editando.set(provedor);
    this.formNome.set(provedor.nome);
    this.formTipoConexao.set(provedor.tipo_conexao);
    this.formBaseUrl.set(provedor.base_url);
    this.formApiKey.set('');
    this.formProjetoId.set(provedor.projeto_id);
    this.formModelo.set(provedor.modelo);
    this.formEstiloApi.set(provedor.estilo_api);
    this.formPrecoEntrada.set(String(provedor.preco_entrada_por_1k));
    this.formPrecoSaida.set(String(provedor.preco_saida_por_1k));
    this.formMoeda.set(provedor.moeda);
    this.erroForm.set(null);
    this.dialogAberto.set(true);
  }

  fecharDialog(): void {
    if (this.salvando()) {
      return;
    }
    this.dialogAberto.set(false);
  }

  abrirTour(): void {
    this.tourAberto.set(true);
  }

  fecharTour(): void {
    this.tourAberto.set(false);
  }

  salvar(): void {
    if (!this.formNome().trim() || !this.formBaseUrl().trim() || !this.formModelo().trim()) {
      this.erroForm.set('Preencha nome, endereço e modelo.');
      return;
    }

    const precoEntrada = this.precoEntradaValido();
    const precoSaida = this.precoSaidaValido();
    if (precoEntrada === null || precoSaida === null) {
      this.erroForm.set('Informe os preços como números maiores ou iguais a 0.');
      return;
    }

    const corpo: Record<string, unknown> = {
      nome: this.formNome().trim(),
      tipo_conexao: this.formTipoConexao(),
      base_url: this.formBaseUrl().trim(),
      projeto_id: this.formProjetoId().trim(),
      modelo: this.formModelo().trim(),
      estilo_api: this.formEstiloApi(),
      preco_entrada_por_1k: precoEntrada,
      preco_saida_por_1k: precoSaida,
      moeda: this.formMoeda().trim() || 'R$',
    };

    const editando = this.editando();
    // Vazio na edição = "não mexe na chave que já está lá" (o backend só
    // sobrescreve quando o campo vem no corpo); na criação, vazio é uma
    // chave vazia mesmo (alguns Ollama locais não pedem autenticação).
    if (!editando || this.formApiKey()) {
      corpo['api_key'] = this.formApiKey();
    }

    this.salvando.set(true);
    this.erroForm.set(null);

    const requisicao = editando
      ? this.http.patch<ProvedorLlm>(`${URL_PROVEDORES}/${editando.id}`, corpo)
      : this.http.post<ProvedorLlm>(URL_PROVEDORES, corpo);

    requisicao.subscribe({
      next: () => {
        this.salvando.set(false);
        this.dialogAberto.set(false);
        this.carregarProvedores();
      },
      error: (erro: HttpErrorResponse) => {
        this.erroForm.set(mensagemErro(erro, 'Não foi possível salvar o provedor.'));
        this.salvando.set(false);
      },
    });
  }

  ativar(provedor: ProvedorLlm): void {
    if (this.ativandoId()) {
      return;
    }
    this.ativandoId.set(provedor.id);
    this.erro.set(null);

    this.http.post<ProvedorLlm[]>(`${URL_PROVEDORES}/${provedor.id}/ativar`, {}).subscribe({
      next: (provedores) => {
        this.provedores.set(provedores);
        this.ativandoId.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível ativar o provedor.'));
        this.ativandoId.set(null);
      },
    });
  }

  /** Volta pro fallback do Ollama do `.env` sem apagar nenhum provedor
   * cadastrado — diferente de `apagar`, que perde o cadastro. */
  desativar(provedor: ProvedorLlm): void {
    if (this.desativandoId()) {
      return;
    }
    this.desativandoId.set(provedor.id);
    this.erro.set(null);

    this.http.post<ProvedorLlm[]>(`${URL_PROVEDORES}/desativar`, {}).subscribe({
      next: (provedores) => {
        this.provedores.set(provedores);
        this.desativandoId.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível desativar o provedor.'));
        this.desativandoId.set(null);
      },
    });
  }

  apagar(provedor: ProvedorLlm): void {
    if (this.apagandoId()) {
      return;
    }
    this.provedorParaApagar.set(provedor);
  }

  cancelarApagar(): void {
    if (this.apagandoId()) {
      return;
    }
    this.provedorParaApagar.set(null);
  }

  confirmarApagar(): void {
    const provedor = this.provedorParaApagar();
    if (!provedor || this.apagandoId()) {
      return;
    }

    this.apagandoId.set(provedor.id);
    this.erro.set(null);

    this.http.delete(`${URL_PROVEDORES}/${provedor.id}`).subscribe({
      next: () => {
        this.provedores.update((atual) => atual.filter((item) => item.id !== provedor.id));
        this.apagandoId.set(null);
        this.provedorParaApagar.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível apagar o provedor.'));
        this.apagandoId.set(null);
      },
    });
  }

  protected rotuloCusto(custo: number | null, moeda: string | null, custoBrl: number | null): string {
    return custo !== null && moeda !== null ? formatarCusto(custo, moeda, custoBrl) : '—';
  }

  protected rotuloTipoConexao(tipo: TipoConexaoLlm): string {
    return tipo === 'ollama' ? 'Ollama' : 'Compatível com OpenAI';
  }

  protected salvarTeto(): void {
    const teto = this.tetoValido();
    if (teto === null || this.salvandoTeto()) {
      return;
    }

    this.salvandoTeto.set(true);
    this.erroTeto.set(null);
    const alteracoes: AlteracoesConfiguracoesTi = { teto_tokens_diario: teto };
    this.configuracoes.salvar(alteracoes).subscribe({
      next: () => {
        this.salvandoTeto.set(false);
        this.configuracoesAbertas.set(false);
      },
      error: (erro: HttpErrorResponse) => {
        this.erroTeto.set(mensagemErro(erro, 'Não foi possível salvar o teto de tokens.'));
        this.salvandoTeto.set(false);
      },
    });
  }
}
