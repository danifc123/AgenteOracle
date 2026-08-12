import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { ConfirmacaoDialog } from '../../../../componentes/confirmacao-dialog/confirmacao-dialog';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { mensagemErro } from '../../../../servicos/mensagens-erro';
import { AnaliseCurriculo, VagaCritica } from '../../../../servicos/analise-curriculo';

/** CRUD de vagas críticas do RH — mesma estrutura de `pages/usuarios/`
 * (tabela + dialog de criação/edição + `ConfirmacaoDialog` pra apagar).
 * Depois de qualquer mutação, chama `AnaliseCurriculo.carregarVagas()` pra
 * a tela `/rh` (que usa o mesmo serviço) enxergar a lista atualizada sem
 * precisar recarregar a página. */
@Component({
  selector: 'app-cadastrar-vagas',
  imports: [Botao, ConfirmacaoDialog, Dialog, ModuloHeader],
  templateUrl: './cadastrar-vagas.html',
  styleUrl: './cadastrar-vagas.scss',
})
export class CadastrarVagas {
  private readonly http = inject(HttpClient);
  protected readonly analiseCurriculo = inject(AnaliseCurriculo);

  protected readonly erro = signal<string | null>(null);

  protected readonly dialogAberto = signal(false);
  protected readonly editando = signal<VagaCritica | null>(null);
  protected readonly salvando = signal(false);
  protected readonly erroForm = signal<string | null>(null);

  protected readonly vagaParaApagar = signal<VagaCritica | null>(null);
  protected readonly apagandoId = signal<number | null>(null);

  protected readonly formTitulo = signal('');
  protected readonly formLocalizacao = signal('');

  protected readonly mensagemConfirmacaoApagar = computed(() => {
    const vaga = this.vagaParaApagar();
    return vaga ? `Apagar a vaga "${vaga.titulo}"? Essa ação não pode ser desfeita.` : '';
  });

  constructor() {
    this.analiseCurriculo.carregarVagas();
  }

  protected abrirDialogEdicao(vaga: VagaCritica): void {
    this.editando.set(vaga);
    this.formTitulo.set(vaga.titulo);
    this.formLocalizacao.set(vaga.localizacao);
    this.erroForm.set(null);
    this.dialogAberto.set(true);
  }

  protected abrirDialogNova(): void {
    this.editando.set(null);
    this.formTitulo.set('');
    this.formLocalizacao.set('');
    this.erroForm.set(null);
    this.dialogAberto.set(true);
  }

  protected alternarAtiva(vaga: VagaCritica): void {
    this.http
      .patch<VagaCritica>(`${MCP_API_BASE_URL}/api/rh/vagas/${vaga.id}`, { ativa: !vaga.ativa })
      .subscribe({
        next: () => this.analiseCurriculo.carregarVagas(),
        error: (erro: HttpErrorResponse) => this.erro.set(mensagemErro(erro, 'Não foi possível atualizar a vaga.')),
      });
  }

  protected apagar(vaga: VagaCritica): void {
    if (this.apagandoId()) {
      return;
    }
    this.vagaParaApagar.set(vaga);
  }

  protected cancelarApagar(): void {
    if (this.apagandoId()) {
      return;
    }
    this.vagaParaApagar.set(null);
  }

  protected confirmarApagar(): void {
    const vaga = this.vagaParaApagar();
    if (!vaga || this.apagandoId()) {
      return;
    }

    this.apagandoId.set(vaga.id);
    this.erro.set(null);

    this.http.delete(`${MCP_API_BASE_URL}/api/rh/vagas/${vaga.id}`).subscribe({
      next: () => {
        this.apagandoId.set(null);
        this.vagaParaApagar.set(null);
        this.analiseCurriculo.carregarVagas();
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível apagar a vaga.'));
        this.apagandoId.set(null);
      },
    });
  }

  protected fecharDialog(): void {
    if (this.salvando()) {
      return;
    }
    this.dialogAberto.set(false);
  }

  protected salvar(): void {
    const titulo = this.formTitulo().trim();
    const localizacao = this.formLocalizacao().trim();
    if (!titulo || !localizacao) {
      this.erroForm.set('Preencha título e localização.');
      return;
    }

    this.salvando.set(true);
    this.erroForm.set(null);

    const vagaEditando = this.editando();
    const requisicao = vagaEditando
      ? this.http.patch<VagaCritica>(`${MCP_API_BASE_URL}/api/rh/vagas/${vagaEditando.id}`, {
          titulo,
          localizacao,
        })
      : this.http.post<VagaCritica>(`${MCP_API_BASE_URL}/api/rh/vagas`, { titulo, localizacao });

    requisicao.subscribe({
      next: () => {
        this.salvando.set(false);
        this.dialogAberto.set(false);
        this.analiseCurriculo.carregarVagas();
      },
      error: (erro: HttpErrorResponse) => {
        this.erroForm.set(mensagemErro(erro, 'Não foi possível salvar a vaga.'));
        this.salvando.set(false);
      },
    });
  }
}
