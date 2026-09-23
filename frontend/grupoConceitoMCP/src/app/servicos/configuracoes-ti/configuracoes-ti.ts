import { HttpClient, HttpContext } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { MCP_API_BASE_URL } from '../../app-config';
import { TOAST_DESATIVADO } from '../toast.interceptor/toast.interceptor';

/** Ollama roda local (ou numa IA em nuvem por fora, via `OLLAMA_HOST_TI`);
 * OCI Generative AI é o serviço liberado pelo suporte Oracle da empresa. */
export type ProvedorIa = 'ollama' | 'oci_openai';

export interface ConfiguracoesTiResposta {
  usar_ia_avaliacao_chamado: boolean;
  percentual_amostragem_chamados: number;
  percentual_alterado_em: string | null;
  ler_chamados_antigos: boolean;
  provedor_ia: ProvedorIa;
  /** Vazio = usa o padrão do provedor ativo. */
  modelo_ia: string;
  /** `0` = sem teto — ver `tools/ia/configuracoes_provedor.py::teto_tokens_diario`. */
  teto_tokens_diario: number;
}

/** Só as chaves que mudaram (o backend valida tudo antes de gravar). */
export type AlteracoesConfiguracoesTi = Partial<
  Pick<
    ConfiguracoesTiResposta,
    | 'usar_ia_avaliacao_chamado'
    | 'percentual_amostragem_chamados'
    | 'ler_chamados_antigos'
    | 'provedor_ia'
    | 'modelo_ia'
    | 'teto_tokens_diario'
  >
>;

const URL_CONFIGURACOES = `${MCP_API_BASE_URL}/api/ti/configuracoes`;

/** Configurações da Auditoria de Chamados; os signals só mudam com a resposta do servidor. */
@Injectable({ providedIn: 'root' })
export class ConfiguracoesTi {
  private readonly http = inject(HttpClient);

  readonly usarIaAvaliacaoChamado = signal(true);
  readonly percentualAmostragemChamados = signal(100);
  readonly percentualAlteradoEm = signal<string | null>(null);
  readonly lerChamadosAntigos = signal(false);
  readonly provedorIa = signal<ProvedorIa>('ollama');
  readonly modeloIa = signal('');
  readonly tetoTokensDiario = signal(0);

  private aplicar(resposta: ConfiguracoesTiResposta): void {
    this.usarIaAvaliacaoChamado.set(resposta.usar_ia_avaliacao_chamado);
    this.percentualAmostragemChamados.set(resposta.percentual_amostragem_chamados);
    this.percentualAlteradoEm.set(resposta.percentual_alterado_em);
    this.lerChamadosAntigos.set(resposta.ler_chamados_antigos);
    this.provedorIa.set(resposta.provedor_ia);
    this.modeloIa.set(resposta.modelo_ia);
    this.tetoTokensDiario.set(resposta.teto_tokens_diario);
  }

  carregar(): void {
    this.http.get<ConfiguracoesTiResposta>(URL_CONFIGURACOES).subscribe({
      next: (resposta) => this.aplicar(resposta),
    });
  }

  /** Sem toast automático: o dialog mostra o sucesso e mantém o erro visível. */
  salvar(alteracoes: AlteracoesConfiguracoesTi): Observable<ConfiguracoesTiResposta> {
    return this.http
      .patch<ConfiguracoesTiResposta>(URL_CONFIGURACOES, alteracoes, {
        context: new HttpContext().set(TOAST_DESATIVADO, true),
      })
      .pipe(tap((resposta) => this.aplicar(resposta)));
  }
}
