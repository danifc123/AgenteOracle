import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { CampoNumerico } from '../../../../componentes/campo-numerico/campo-numerico';
import { ConfirmacaoDialog } from '../../../../componentes/confirmacao-dialog/confirmacao-dialog';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../../../componentes/select-busca/select-busca';
import { Selo } from '../../../../componentes/selo/selo';
import { mensagemErro } from '../../../../servicos/mensagens-erro/mensagens-erro';

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

const URL_PROVEDORES = `${MCP_API_BASE_URL}/api/ti/provedores-llm`;

/** Preço aceita vírgula ou ponto, sem teto nem limite de casas (o backend
 * usa `Decimal` — só a exibição na lista é que arredonda) — mesmo espírito
 * de `percentualValido` (`servicos/amostragem-chamados`), sem o teto de 100. */
function precoValido(texto: string): number | null {
  const limpo = texto.trim().replace(',', '.');
  return /^\d+(\.\d+)?$/.test(limpo) ? Number(limpo) : null;
}

/** MÓDULO TI — CADASTRO DE LLM (`/ti/provedores`, só desenvolvedor)
 *
 * Substitui os dois provedores fixos no código (Ollama/OCI, cada um com
 * URL e modelo fixos) por um cadastro livre — ver `tools/ia/provedores_llm.py`
 * no backend. Cada linha cadastrada é UMA conexão + UM modelo, e só fala uma
 * de duas "linguagens" (`tipo_conexao`): Ollama nativo, ou qualquer serviço
 * compatível com a API da OpenAI (a OCI inclusa). Dentro da segunda,
 * `estilo_api` escolhe entre Chat Completions (a maioria dos modelos) e
 * Responses API (só quando o modelo exige — confirmado com o suporte
 * Oracle pro gpt-oss-120b). Preço é opcional pra qualquer um dos dois,
 * inclusive Ollama (que não tem custo real em dinheiro) — existe só pra
 * alimentar a estimativa de custo da tela de Tokens.
 *
 * Chave de API nunca volta do backend depois de salva (só o booleano
 * `api_key_configurada`) — editar sem preencher o campo de novo mantém a
 * que já estava lá.
 *
 * Só desenvolvedor acessa (rota protegida por `devGuard`, item do menu
 * escondido de quem não é desenvolvedor via `ItemMenu.soDev`) — o backend
 * (`/api/ti/provedores-llm*`) também exige isso no decorator de cada rota,
 * mais rígido que o resto do TI porque aqui tem segredo de verdade. */
@Component({
  selector: 'app-provedores-llm',
  imports: [
    Botao,
    CampoNumerico,
    ConfirmacaoDialog,
    Dialog,
    EstadoVazio,
    ModuloHeader,
    SelectBusca,
    Selo,
  ],
  templateUrl: './provedores.html',
  styleUrl: './provedores.scss',
})
export class ProvedoresLlm {
  private readonly http = inject(HttpClient);

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

  protected readonly opcoesTipoConexao = OPCOES_TIPO_CONEXAO;
  protected readonly opcoesEstiloApi = OPCOES_ESTILO_API;

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

  constructor() {
    this.carregarProvedores();
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

  protected rotuloTipoConexao(tipo: TipoConexaoLlm): string {
    return tipo === 'ollama' ? 'Ollama' : 'Compatível com OpenAI';
  }
}
