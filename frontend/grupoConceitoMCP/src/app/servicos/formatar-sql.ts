import { format } from 'sql-formatter';

/** Reindenta as linhas que começam com vírgula (uma por coluna, no estilo
 * "vírgula na frente") pra ficarem no mesmo nível da coluna anterior — o
 * `sql-formatter` deixa essas linhas sem indentação por padrão. */
function reindentarVirgulas(sqlFormatado: string): string {
  let indentacaoAnterior = '';

  return sqlFormatado
    .split('\n')
    .map((linha) => {
      if (linha.trimStart().startsWith(',')) {
        return indentacaoAnterior + linha.trimStart();
      }
      indentacaoAnterior = linha.match(/^\s*/)?.[0] ?? '';
      return linha;
    })
    .join('\n');
}

/** Formata uma consulta SQL pra exibição ao usuário (histórico, chat) — uma
 * coluna por linha, vírgula na frente, cada cláusula (FROM/WHERE/GROUP
 * BY/ORDER BY...) na própria linha com o conteúdo indentado embaixo. */
export function formatarSql(sql: string): string {
  const bruto = format(sql, { language: 'postgresql', commaPosition: 'before', tabWidth: 4 });
  return reindentarVirgulas(bruto);
}
