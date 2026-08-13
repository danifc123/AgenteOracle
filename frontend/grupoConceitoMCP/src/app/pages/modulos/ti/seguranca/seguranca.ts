import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../../app-config';
import { Botao } from '../../../../componentes/botao/botao';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { mensagemErro } from '../../../../servicos/mensagens-erro';
import { Sessao } from '../../../../servicos/sessao';

export interface AchadoSeguranca {
  usuario: string;
  sistema: 'agente_oracle' | 'protheus';
  tipo: 'tentativa_invasao' | 'acesso_dados_suspeito';
  descricao: string;
  evidencia: string;
}

interface RegistroHistoricoSeguranca extends AchadoSeguranca {
  execucao_id: string;
  usuario_id: string;
  criado_em: string;
  ativo: boolean;
}

const ROTULOS_TIPO: Record<AchadoSeguranca['tipo'], string> = {
  tentativa_invasao: 'Tentativa de invasão',
  acesso_dados_suspeito: 'Acesso a dado suspeito',
};

const ROTULOS_SISTEMA: Record<AchadoSeguranca['sistema'], string> = {
  agente_oracle: 'AgenteOracle',
  protheus: 'Protheus',
};

/** MÓDULO TI — TELA "SEGURANÇA" (2026-08)
 *
 * Roda sob demanda, mesmo espírito de `pages/auditoria/historico` — mas
 * autocontida (sem depender de um sino/painel compartilhado): "Analisar
 * agora" chama `GET /api/ti/seguranca` (agrega eventos de login recentes
 * + volume de acesso a dado, manda pra IA) e atualiza a lista na hora. O
 * histórico completo (`GET /api/ti/seguranca/historico`) carrega ao abrir
 * a tela, pra já mostrar o que estava pendente de execuções anteriores.
 */
@Component({
  selector: 'app-seguranca-ti',
  imports: [Botao, DatePipe, ModuloHeader],
  templateUrl: './seguranca.html',
  styleUrl: './seguranca.scss',
})
export class SegurancaTi {
  private readonly http = inject(HttpClient);
  protected readonly sessao = inject(Sessao);

  protected readonly achados = signal<AchadoSeguranca[]>([]);
  protected readonly historico = signal<RegistroHistoricoSeguranca[]>([]);
  protected readonly carregandoHistorico = signal(true);
  protected readonly analisando = signal(false);
  protected readonly dispensandoChave = signal<string | null>(null);
  protected readonly erro = signal<string | null>(null);

  protected readonly ehDesenvolvedor = () => this.sessao.papeis().includes('desenvolvedor');

  constructor() {
    this.carregarHistorico();
  }

  private carregarHistorico(): void {
    this.carregandoHistorico.set(true);
    this.http
      .get<RegistroHistoricoSeguranca[]>(`${MCP_API_BASE_URL}/api/ti/seguranca/historico`)
      .subscribe({
        next: (registros) => {
          this.historico.set(registros);
          this.carregandoHistorico.set(false);
        },
        error: () => this.carregandoHistorico.set(false),
      });
  }

  protected analisarAgora(): void {
    if (this.analisando()) {
      return;
    }

    this.analisando.set(true);
    this.erro.set(null);

    this.http.get<AchadoSeguranca[]>(`${MCP_API_BASE_URL}/api/ti/seguranca`).subscribe({
      next: (achados) => {
        this.achados.set(achados);
        this.analisando.set(false);
        this.carregarHistorico();
      },
      error: (erro: HttpErrorResponse) => {
        this.erro.set(mensagemErro(erro, 'Não foi possível rodar a análise de segurança.'));
        this.analisando.set(false);
      },
    });
  }

  protected chaveAchado(achado: AchadoSeguranca): string {
    return `${achado.usuario}|${achado.sistema}|${achado.tipo}`;
  }

  protected dispensar(achado: AchadoSeguranca): void {
    if (this.dispensandoChave()) {
      return;
    }

    const chave = this.chaveAchado(achado);
    this.dispensandoChave.set(chave);
    this.erro.set(null);

    this.http
      .post(`${MCP_API_BASE_URL}/api/ti/seguranca/dispensar`, {
        usuario: achado.usuario,
        sistema: achado.sistema,
        tipo: achado.tipo,
      })
      .subscribe({
        next: () => {
          this.achados.update((atual) => atual.filter((item) => this.chaveAchado(item) !== chave));
          this.dispensandoChave.set(null);
        },
        error: (erro: HttpErrorResponse) => {
          this.erro.set(mensagemErro(erro, 'Não foi possível dispensar o achado.'));
          this.dispensandoChave.set(null);
        },
      });
  }

  protected rotuloSistema(sistema: AchadoSeguranca['sistema']): string {
    return ROTULOS_SISTEMA[sistema];
  }

  protected rotuloTipo(tipo: AchadoSeguranca['tipo']): string {
    return ROTULOS_TIPO[tipo];
  }
}
