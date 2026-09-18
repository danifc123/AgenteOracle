import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { Botao } from '../../componentes/botao/botao';
import { ConfirmacaoDialog } from '../../componentes/confirmacao-dialog/confirmacao-dialog';
import { Dialog } from '../../componentes/dialog/dialog';
import { EstadoVazio } from '../../componentes/estado-vazio/estado-vazio';
import { IconeOrdenacao } from '../../componentes/icone-ordenacao/icone-ordenacao';
import { ModuloHeader } from '../../componentes/modulo-header/modulo-header';
import { OpcaoSelectBusca, SelectBusca } from '../../componentes/select-busca/select-busca';
import { Selo } from '../../componentes/selo/selo';
import { SoDev } from '../../diretivas/so-dev';
import { SoModulo } from '../../diretivas/so-modulo';
import { mensagemErro } from '../../servicos/mensagens-erro';
import { compararValores, DirecaoOrdenacao, proximaDirecao } from '../../servicos/ordenacao-tabela';

interface Usuario {
  id: number;
  usuario: string;
  nome: string;
  papeis: string[];
  ativo: boolean;
  bloqueado: boolean;
}

interface Papel {
  slug: string;
  rotulo: string;
}

interface Filial {
  codigo: string;
  nome: string;
}

interface TecnicoGlpi {
  id: string;
  nome: string;
  titulo: string | null;
}

/** Papéis do módulo Financeiro — únicos com filial de verdade hoje (ver
 * `tools/auth/restricoes_filial.py`). Lista curta e fixa de propósito, não
 * vale a pena buscar do backend só pra isso. */
const PAPEIS_FINANCEIRO = ['financeiro', 'financeiro_admin'];

/** Papéis do módulo TI — mesmo espírito de `PAPEIS_FINANCEIRO` acima.
 * Controla quando mostrar o campo de vínculo com técnico do GLPI (nem todo
 * login de TI é de alguém que atende chamado, por isso o campo continua
 * opcional mesmo aparecendo). */
const PAPEIS_TI = ['ti_admin', 'ti_infraestrutura', 'ti_sistemas', 'ti_processos', 'desenvolvedor'];

@Component({
  selector: 'app-usuarios',
  imports: [
    Botao,
    ConfirmacaoDialog,
    Dialog,
    EstadoVazio,
    IconeOrdenacao,
    ModuloHeader,
    SelectBusca,
    Selo,
    SoDev,
    SoModulo,
  ],
  templateUrl: './usuarios.html',
  styleUrl: './usuarios.scss',
})
export class Usuarios {
  private readonly http = inject(HttpClient);

  usuarios = signal<Usuario[]>([]);
  papeisDisponiveis = signal<Papel[]>([]);
  carregando = signal(true);
  erro = signal<string | null>(null);

  dialogAberto = signal(false);
  criando = signal(false);
  erroForm = signal<string | null>(null);
  usuarioParaApagar = signal<Usuario | null>(null);
  apagandoId = signal<number | null>(null);
  desbloqueandoId = signal<number | null>(null);

  protected readonly mensagemConfirmacaoApagar = computed(() => {
    const usuario = this.usuarioParaApagar();
    return usuario
      ? `Apagar o usuário "${usuario.usuario}"? Essa ação não pode ser desfeita.`
      : '';
  });

  formUsuario = signal('');
  formNome = signal('');
  formSenha = signal('');
  formPapeis = signal<string[]>([]);
  formTecnicoGlpiId = signal<string | null>(null);
  formEmail = signal('');

  tecnicosGlpiDisponiveis = signal<TecnicoGlpi[]>([]);

  filiaisDisponiveis = signal<Filial[]>([]);
  dialogFiliaisAberto = signal(false);
  usuarioFiliais = signal<Usuario | null>(null);
  formFiliaisBloqueadas = signal<string[]>([]);
  carregandoFiliaisBloqueadas = signal(false);
  salvandoFiliais = signal(false);
  erroFiliais = signal<string | null>(null);

  constructor() {
    this.carregarUsuarios();
    this.carregarPapeis();
  }

  protected readonly opcoesFiliais = () =>
    this.filiaisDisponiveis().map(
      (filial): OpcaoSelectBusca => ({ valor: filial.codigo, rotulo: `${filial.codigo} - ${filial.nome}` }),
    );

  protected readonly opcoesPapeis = () =>
    this.papeisDisponiveis().map((papel): OpcaoSelectBusca => ({
      valor: papel.slug,
      rotulo: papel.rotulo,
    }));

  protected readonly opcoesTecnicosGlpi = () =>
    this.tecnicosGlpiDisponiveis().map(
      (tecnico): OpcaoSelectBusca => ({
        valor: tecnico.id,
        rotulo: tecnico.titulo ? `${tecnico.nome} — ${tecnico.titulo}` : tecnico.nome,
      }),
    );

  /** Só aparece pra papel de TI — e, diferente de antes, agora é
   * obrigatório (junto com o e-mail) sempre que aparece: papel de TI sem
   * técnico do GLPI vinculado é rejeitado pelo backend (`usuarios_route`),
   * pra ninguém de outro módulo conseguir criar um login de TI sem
   * registro correspondente no GLPI. Mesmo padrão de `usuarioTemFinanceiro`
   * pra decidir quando mostrar. */
  protected readonly mostrarCampoTecnico = computed(() =>
    this.formPapeis().some((papel) => PAPEIS_TI.includes(papel)),
  );

  protected readonly colunaOrdenada = signal<string | null>(null);
  protected readonly direcaoOrdenacao = signal<DirecaoOrdenacao>(null);

  protected readonly usuariosOrdenados = computed(() => {
    const coluna = this.colunaOrdenada();
    const direcao = this.direcaoOrdenacao();
    const lista = this.usuarios();
    if (!coluna || !direcao) {
      return lista;
    }

    const sinal = direcao === 'asc' ? 1 : -1;
    return [...lista].sort(
      (a, b) => compararValores(this.valorColuna(a, coluna), this.valorColuna(b, coluna)) * sinal,
    );
  });

  private carregarFiliaisDisponiveis(): void {
    if (this.filiaisDisponiveis().length) {
      return;
    }
    this.http.get<Filial[]>(`${MCP_API_BASE_URL}/api/financeiro/filiais`).subscribe({
      next: (filiais) => this.filiaisDisponiveis.set(filiais),
      error: () => this.filiaisDisponiveis.set([]),
    });
  }

  private carregarPapeis(): void {
    this.http.get<Papel[]>(`${MCP_API_BASE_URL}/api/auth/papeis`).subscribe({
      next: (papeis) => this.papeisDisponiveis.set(papeis),
      error: () => this.papeisDisponiveis.set([]),
    });
  }

  private carregarTecnicosGlpiDisponiveis(): void {
    if (this.tecnicosGlpiDisponiveis().length) {
      return;
    }
    this.http.get<TecnicoGlpi[]>(`${MCP_API_BASE_URL}/api/ti/tecnicos-glpi`).subscribe({
      next: (tecnicos) => this.tecnicosGlpiDisponiveis.set(tecnicos),
      error: () => this.tecnicosGlpiDisponiveis.set([]),
    });
  }

  private valorColuna(usuario: Usuario, coluna: string): unknown {
    switch (coluna) {
      case 'usuario':
        return usuario.usuario;
      case 'nome':
        return usuario.nome;
      case 'papeis':
        return this.rotuloPapeis(usuario.papeis);
      case 'status':
        return usuario.bloqueado ? 2 : usuario.ativo ? 1 : 0;
      default:
        return '';
    }
  }

  abrirDialog(): void {
    this.formUsuario.set('');
    this.formNome.set('');
    this.formSenha.set('');
    this.formPapeis.set([]);
    this.formTecnicoGlpiId.set(null);
    this.formEmail.set('');
    this.erroForm.set(null);
    this.dialogAberto.set(true);
    this.carregarTecnicosGlpiDisponiveis();
  }

  abrirDialogFiliais(usuario: Usuario): void {
    this.usuarioFiliais.set(usuario);
    this.erroFiliais.set(null);
    this.formFiliaisBloqueadas.set([]);
    this.dialogFiliaisAberto.set(true);
    this.carregarFiliaisDisponiveis();

    this.carregandoFiliaisBloqueadas.set(true);
    this.http
      .get<{ filiais: string[] }>(
        `${MCP_API_BASE_URL}/api/auth/usuarios/${usuario.id}/filiais-bloqueadas`,
        { params: { modulo: 'financeiro' } },
      )
      .subscribe({
        next: (resposta) => {
          this.formFiliaisBloqueadas.set(resposta.filiais);
          this.carregandoFiliaisBloqueadas.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroFiliais.set(mensagemErro(erro, 'Não foi possível carregar as filiais bloqueadas.'));
          this.carregandoFiliaisBloqueadas.set(false);
        },
      });
  }

  apagarUsuario(usuario: Usuario): void {
    if (this.apagandoId()) {
      return;
    }
    this.usuarioParaApagar.set(usuario);
  }

  cancelarApagarUsuario(): void {
    if (this.apagandoId()) {
      return;
    }
    this.usuarioParaApagar.set(null);
  }

  carregarUsuarios(): void {
    this.carregando.set(true);
    this.erro.set(null);

    this.http.get<Usuario[]>(`${MCP_API_BASE_URL}/api/auth/usuarios`).subscribe({
      next: (usuarios) => {
        this.usuarios.set(usuarios);
        this.carregando.set(false);
      },
      error: () => {
        this.erro.set('Não foi possível carregar os usuários.');
        this.carregando.set(false);
      },
    });
  }

  confirmarApagarUsuario(): void {
    const usuario = this.usuarioParaApagar();
    if (!usuario || this.apagandoId()) {
      return;
    }

    this.apagandoId.set(usuario.id);
    this.erro.set(null);

    this.http.delete(`${MCP_API_BASE_URL}/api/auth/usuarios/${usuario.id}`).subscribe({
      next: () => {
        this.usuarios.update((atual) => atual.filter((item) => item.id !== usuario.id));
        this.apagandoId.set(null);
        this.usuarioParaApagar.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível apagar o usuário.'));
        this.apagandoId.set(null);
      },
    });
  }

  criarUsuario(): void {
    if (
      !this.formUsuario().trim() ||
      !this.formNome().trim() ||
      !this.formSenha().trim() ||
      !this.formPapeis().length
    ) {
      this.erroForm.set('Preencha usuário, nome, senha e ao menos um papel.');
      return;
    }

    // Campo visível (papel de TI selecionado) = campo obrigatório — a regra
    // de QUAL papel exige o quê mora só no backend (`usuarios_route`), aqui
    // só evita a viagem ao servidor pra um erro óbvio.
    if (this.mostrarCampoTecnico() && (!this.formTecnicoGlpiId() || !this.formEmail().trim())) {
      this.erroForm.set('Papel de TI exige técnico do GLPI vinculado e o e-mail dessa pessoa.');
      return;
    }

    this.criando.set(true);
    this.erroForm.set(null);

    this.http
      .post<Usuario>(`${MCP_API_BASE_URL}/api/auth/usuarios`, {
        usuario: this.formUsuario().trim(),
        nome: this.formNome().trim(),
        senha: this.formSenha(),
        papeis: this.formPapeis(),
        tecnico_glpi_id: this.formTecnicoGlpiId(),
        email: this.formEmail().trim() || null,
      })
      .subscribe({
        next: () => {
          this.criando.set(false);
          this.dialogAberto.set(false);
          this.carregarUsuarios();
        },
        error: (erro: HttpErrorResponse) => {
          this.erroForm.set(mensagemErro(erro, 'Não foi possível criar o usuário.'));
          this.criando.set(false);
        },
      });
  }

  desbloquearUsuario(usuario: Usuario): void {
    if (this.desbloqueandoId()) {
      return;
    }

    this.desbloqueandoId.set(usuario.id);
    this.erro.set(null);

    this.http
      .patch(`${MCP_API_BASE_URL}/api/auth/usuarios/${usuario.id}/desbloquear`, {})
      .subscribe({
        next: () => {
          this.usuarios.update((atual) =>
            atual.map((item) => (item.id === usuario.id ? { ...item, bloqueado: false } : item)),
          );
          this.desbloqueandoId.set(null);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível desbloquear o usuário.'));
          this.desbloqueandoId.set(null);
        },
      });
  }

  protected direcaoDaColuna(coluna: string): DirecaoOrdenacao {
    return this.colunaOrdenada() === coluna ? this.direcaoOrdenacao() : null;
  }

  fecharDialog(): void {
    if (this.criando()) {
      return;
    }
    this.dialogAberto.set(false);
  }

  fecharDialogFiliais(): void {
    if (this.salvandoFiliais()) {
      return;
    }
    this.dialogFiliaisAberto.set(false);
  }

  protected ordenarPor(coluna: string): void {
    if (this.colunaOrdenada() === coluna) {
      this.direcaoOrdenacao.set(proximaDirecao(this.direcaoOrdenacao()));
    } else {
      this.colunaOrdenada.set(coluna);
      this.direcaoOrdenacao.set('asc');
    }
  }

  protected rotuloPapeis(slugs: string[]): string {
    const disponiveis = this.papeisDisponiveis();
    return slugs
      .map((slug) => disponiveis.find((papel) => papel.slug === slug)?.rotulo ?? slug)
      .join(', ');
  }

  salvarFiliaisBloqueadas(): void {
    const usuario = this.usuarioFiliais();
    if (!usuario || this.salvandoFiliais()) {
      return;
    }

    this.salvandoFiliais.set(true);
    this.erroFiliais.set(null);

    this.http
      .put<{ filiais: string[] }>(`${MCP_API_BASE_URL}/api/auth/usuarios/${usuario.id}/filiais-bloqueadas`, {
        modulo: 'financeiro',
        filiais: this.formFiliaisBloqueadas(),
      })
      .subscribe({
        next: () => {
          this.salvandoFiliais.set(false);
          this.dialogFiliaisAberto.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroFiliais.set(mensagemErro(erro, 'Não foi possível salvar as filiais bloqueadas.'));
          this.salvandoFiliais.set(false);
        },
      });
  }

  /** Só usuários do Financeiro têm filial de verdade hoje — botão
   * "Gerenciar filiais" some da linha de quem não tem nenhum papel desse
   * módulo (RH, Estoque ainda não usam filial). */
  protected usuarioTemFinanceiro(usuario: Usuario): boolean {
    return usuario.papeis.some((papel) => PAPEIS_FINANCEIRO.includes(papel));
  }
}
